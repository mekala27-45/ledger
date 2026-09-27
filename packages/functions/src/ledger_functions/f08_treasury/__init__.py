"""Function 8: treasury and stress testing.

Question: what does a rate move do to net interest income, what would the Federal
Reserve's 2026 scenarios do to the loan book and to capital, and how long would the
bank's liquid assets last?

Method: repricing gaps over twelve months with the deposit betas from function 6 and the
loan book's observed runoff; a macro link from unemployment and house price growth to the
monthly roll into delinquency, fitted on the generator's thirty six months and required
to recover the generator's stated sensitivity; the supervisory scenarios applied as
changes from their jump off point to the bank's own starting conditions for nine
quarters, with intervals from the link's uncertainty; and a simplified liquidity coverage
figure. These are illustrative projections on a fictional bank in the shape of the
supervisory exercise, not the exercise.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import polars as pl
from ledger_core.formats import format_value
from ledger_core.manifest import Manifest, Scalar
from ledger_stress.link import fit_link, project, scenario_changes
from ledger_stress.nii import Position, even_runoff_weight, maturity_weight, nii_change

from ledger_functions.base import Context, FunctionSpec

SCENARIOS = {"baseline": "Baseline", "severely_adverse": "Severely adverse"}
JUMP_OFF = "2025Q4"
# The rate sheet never offers a certificate under half a percent.
TIME_FLOOR = 0.50
LINK_TOLERANCE = 0.10
UNSECURED = ("installment", "card")
TERM_NAMES = {
    "const": "Intercept",
    "unemployment": "Unemployment, per point above four",
    "hpi_growth": "House price growth, per point a year",
    "loose_vintage": "The loose underwriting vintages",
    "card": "Card rather than installment",
    "mob_6_11": "Six to eleven months on book",
    "mob_12_23": "Twelve to twenty three months on book",
    "mob_24_plus": "Two years or more on book",
}


def _floats(row: dict[str, Any]) -> dict[str, Any]:
    """Decimals from the warehouse as floats; everything else as it is."""
    from decimal import Decimal

    return {k: float(v) if isinstance(v, Decimal) else v for k, v in row.items()}


def quarters_after(jump_off: str, n: int) -> list[str]:
    year, q = int(jump_off[:4]), int(jump_off[-1])
    out = []
    for _ in range(n):
        q += 1
        if q == 5:
            year, q = year + 1, 1
        out.append(f"{year}Q{q}")
    return out


def run(ctx: Context) -> None:
    m = ctx.manifest
    cfg = ctx.config
    as_of = cfg.calendar.as_of.strftime("%Y-%m")
    gen: dict[str, Any] = {
        "backend": "generated",
        "population": f"Harborline's balance sheet as of {as_of}",
        "source": "marts.mart_balance_sheet_monthly",
    }
    truth = json.loads((ctx.paths.raw / "truth" / "truth_parameters.json").read_text())
    bs = _floats(
        ctx.sql(f"select * from marts.mart_balance_sheet_monthly where month = '{as_of}'").row(0, named=True)
    )
    sheet = _floats(
        ctx.sql(f"select * from staging.stg_deposit_rates where month = '{as_of}'").row(0, named=True)
    )
    macro_now = _floats(
        ctx.sql(f"select * from staging.stg_macro_path where month = '{as_of}'").row(0, named=True)
    )
    horizon = cfg.treasury.horizon_months

    # ---- Rate sensitivity -------------------------------------------------------------
    book = ctx.sql(
        f"""
        select product, sum(opening_balance)::double as balance, sum(amount_paid - interest_paid)::double as principal
        from marts.fct_loan_month
        where month > strftime(date '{cfg.calendar.as_of}' - interval 12 month, '%Y-%m')
        group by 1
        """
    )
    months_in_window = 12
    share = {
        r["product"]: min(1.0, r["principal"] / (r["balance"] / months_in_window))
        for r in book.iter_rows(named=True)
    }
    cds = ctx.sql(
        f"""
        select date_diff('month', date '{cfg.calendar.as_of}', a.open_date + to_months(a.term_months::int)) as months_left,
            b.closing_balance::double as balance
        from staging.stg_deposit_balances b join marts.dim_deposit_account a using (account_id)
        where a.product = 'time' and b.month = '{as_of}' and not b.closed_this_month
        """
    )
    cd_weight = maturity_weight(
        [max(0, int(k)) for k in cds["months_left"].to_list()], cds["balance"].to_list(), horizon
    )
    cd_share_in_year = float(cds.filter(pl.col("months_left") < horizon)["balance"].sum()) / float(
        cds["balance"].sum()
    )
    deposits = Manifest.load(ctx.paths.results / "f06" / "manifest.json")
    betas = {p: float(deposits.raw(f"f06.beta_{p}")) for p in ("checking", "savings", "time")}  # type: ignore[arg-type]
    floors = {
        "checking": truth["betas"]["checking_floor"],
        "savings": truth["betas"]["savings_floor"],
        "time": TIME_FLOOR,
    }
    ladder = 1.0 / cfg.treasury.securities_ladder_years
    positions = [
        Position("Cash", "asset", bs["cash"], 1.0, room_down=macro_now["policy_rate"]),
        Position("Securities", "asset", bs["securities"], even_runoff_weight(ladder, horizon)),
        Position("Card loans", "asset", bs["loans_card"], 1.0),
        Position(
            "Installment loans",
            "asset",
            bs["loans_installment"],
            even_runoff_weight(min(1.0, share["installment"]), horizon),
        ),
        Position(
            "Mortgages",
            "asset",
            bs["loans_mortgage"],
            even_runoff_weight(min(1.0, share["mortgage"]), horizon),
        ),
        Position(
            "Checking",
            "liability",
            bs["deposits_checking"],
            1.0,
            beta=betas["checking"],
            room_down=max(0.0, sheet["checking_rate"] - floors["checking"]),
        ),
        Position(
            "Savings",
            "liability",
            bs["deposits_savings"],
            1.0,
            beta=betas["savings"],
            room_down=max(0.0, sheet["savings_rate"] - floors["savings"]),
        ),
        Position(
            "Time deposits",
            "liability",
            bs["deposits_time"],
            cd_weight,
            beta=betas["time"],
            room_down=max(0.0, sheet["time_rate"] - floors["time"]),
        ),
    ]
    base_nii = float(
        ctx.sql(
            f"""
            select sum(interest_income_loans + interest_income_securities - interest_expense_deposits
                - interest_expense_borrowings)::double as nii
            from marts.mart_income_statement_monthly
            where month > strftime(date '{cfg.calendar.as_of}' - interval 12 month, '%Y-%m')
            """
        )["nii"][0]
    )
    m.put("f08.base_nii", base_nii, "usdm", **gen)
    rows: list[list[Scalar]] = []
    detail: dict[int, dict[str, float]] = {}
    for shock in sorted(cfg.treasury.shocks_bps):
        change = nii_change(positions, shock)
        detail[shock] = change
        assets = sum(change[p.name] for p in positions if p.side == "asset")
        liabilities = sum(change[p.name] for p in positions if p.side == "liability")
        rows.append([shock, change["total"], change["total"] / base_nii, assets, liabilities])
        tag = f"{'up' if shock > 0 else 'down'}{abs(shock)}"
        m.put(f"f08.nii_{tag}", change["total"], "usd0", **gen)
        m.put(f"f08.nii_{tag}_share", change["total"] / base_nii, "spct1", **gen)
    frame = pl.DataFrame(
        rows, schema=["shock_bps", "nii_change", "share_of_nii", "assets", "deposits"], orient="row"
    )
    ctx.save("nii_shocks", frame)
    m.put_table(
        "f08.nii_table",
        [
            "Parallel shock",
            "Change in net interest income",
            "Share of the last twelve months",
            "From assets",
            "From deposits",
        ],
        ["int", "usd0", "spct1", "usd0", "usd0"],
        rows,
        **gen,
    )
    by_position = pl.DataFrame(
        {
            "position": [p.name for p in positions],
            "side": [p.side for p in positions],
            "balance": [p.balance for p in positions],
            "weight": [p.weight for p in positions],
            "beta": [p.beta for p in positions],
            **{f"shock_{s}": [detail[s][p.name] for p in positions] for s in sorted(detail)},
        }
    )
    ctx.save("nii_positions", by_position)
    m.put_table(
        "f08.repricing",
        [
            "Position",
            "Balance",
            "Repricing weight in twelve months",
            "Beta",
            "Change at +200 bp",
            "Change at -200 bp",
        ],
        ["text", "usdm", "pct1", "float2", "usd0", "usd0"],
        [
            [p.name, p.balance, p.weight, p.beta, detail[max(detail)][p.name], detail[min(detail)][p.name]]
            for p in positions
        ],
        **gen,
    )
    m.put("f08.cd_share_in_year", cd_share_in_year, "pct1", **gen)
    m.put("f08.installment_runoff", min(1.0, share["installment"]), "pct1", **gen)
    m.put("f08.mortgage_runoff", min(1.0, share["mortgage"]), "pct1", **gen)
    m.put("f08.securities_ladder_years", cfg.treasury.securities_ladder_years, "float1", **gen)
    up, down = max(detail), min(detail)
    relative = detail[up]["total"] / base_nii
    if abs(relative) < 0.01:
        stance = (
            "The balance sheet is close to neutral: what the assets gain from a rise, the deposits give back, because "
            "savings pass on a large share of any move and most certificates reprice within the year."
        )
    elif relative > 0:
        stance = "The bank is asset sensitive: its assets reprice faster than its deposits."
    else:
        stance = "The bank is liability sensitive: its deposits reprice faster than its assets."
    m.put(
        "f08.stance",
        "close to neutral"
        if abs(relative) < 0.01
        else ("asset sensitive" if relative > 0 else "liability sensitive"),
        "text",
        **gen,
    )
    m.put_figure(
        "f08.fig_nii",
        "Net interest income over twelve months, parallel rate shocks",
        f"Against {format_value(base_nii, 'usdm')} of net interest income over the last twelve months, a {up} basis "
        f"point rise changes it by {format_value(detail[up]['total'], 'usd0')} and a {abs(down)} basis point fall by "
        f"{format_value(detail[down]['total'], 'usd0')}. {stance} The fall costs more than the rise earns because "
        "checking is already at its floor and cannot follow rates down. Balances are held flat and customer "
        "behaviour does not change with the shock.",
        data="f08/nii_shocks.parquet",
        **gen,
    )

    # ---- The macro link ----------------------------------------------------------------
    loose = list(truth["default"]["loose_vintages"])
    cells = ctx.sql(
        f"""
        select l.month, l.product,
            (l.vintage in (select unnest(?)))::int as loose_vintage,
            case when l.months_on_book < 6 then 'a' when l.months_on_book < 12 then 'b'
                 when l.months_on_book < 24 then 'c' else 'd' end as mob,
            count(*) as exposed,
            count(*) filter (where l.bucket = '30') as rolled,
            any_value(p.unemployment_rate) - 4.0 as unemployment,
            any_value(p.hpi_growth_annualised) * 100 as hpi_growth
        from marts.fct_loan_month l join staging.stg_macro_path p using (month)
        where l.bucket_open = 'current' and l.product in {UNSECURED}
        group by 1, 2, 3, 4
        """,
        [loose],
    ).with_columns(
        card=(pl.col("product") == "card").cast(pl.Float64),
        mob_6_11=(pl.col("mob") == "b").cast(pl.Float64),
        mob_12_23=(pl.col("mob") == "c").cast(pl.Float64),
        mob_24_plus=(pl.col("mob") == "d").cast(pl.Float64),
        loose_vintage=pl.col("loose_vintage").cast(pl.Float64),
    )
    fit = fit_link(cells)
    stated = float(truth["default"]["beta_macro"])
    b_u, (u_lo, u_hi) = fit.coef("unemployment"), fit.interval("unemployment")
    b_h, (h_lo, h_hi) = fit.coef("hpi_growth"), fit.interval("hpi_growth")
    within = abs(b_u - stated) <= LINK_TOLERANCE
    link: dict[str, Any] = {**gen, "source": "ledger_stress.link, loan months September 2023 to August 2026"}
    m.put("f08.link_unemployment", b_u, "float3", **link)
    m.put("f08.link_unemployment_low", u_lo, "float3", **link)
    m.put("f08.link_unemployment_high", u_hi, "float3", **link)
    m.put("f08.link_stated", stated, "float2", **link)
    m.put("f08.link_tolerance", LINK_TOLERANCE, "float2", **link)
    m.put("f08.link_within", "yes" if within else "no", "text", **link)
    m.put("f08.link_hpi", b_h, "float3", **link)
    m.put("f08.link_hpi_low", h_lo, "float3", **link)
    m.put("f08.link_hpi_high", h_hi, "float3", **link)
    m.put("f08.link_loan_months", fit.n_loan_months, "int", **link)
    m.put("f08.link_rolls", fit.events, "int", **link)
    m.put_table(
        "f08.link_table",
        ["Term", "Coefficient", "Low", "High"],
        ["text", "float3", "float3", "float3"],
        [[TERM_NAMES[name], float(fit.params[i]), *fit.interval(name)] for i, name in enumerate(fit.names)],
        **link,
    )
    if not within:
        raise RuntimeError(
            f"the macro link recovered {b_u:.3f} per point of unemployment against the generator's {stated}; "
            "no scenario is projected from a link that fails its known parameter check"
        )

    # ---- Supervisory scenarios -----------------------------------------------------------
    scen = ctx.sql("select * from marts.mart_scenarios")
    n_q = cfg.treasury.stress_quarters
    quarters = quarters_after(JUMP_OFF, n_q)
    recent = ctx.sql(
        f"""
        select product, count(*) filter (where bucket = '30')::double / count(*) as h0
        from marts.fct_loan_month
        where bucket_open = 'current' and product in {UNSECURED}
            and month > strftime(date '{cfg.calendar.as_of}' - interval 3 month, '%Y-%m')
        group by 1
        """
    )
    h0 = dict(recent.iter_rows())
    history = ctx.sql(
        """
        select product,
            count(*) filter (where bucket_open = 'current' and bucket = '30')::double as rolls,
            count(*) filter (where bucket = 'charged_off' and bucket_open <> 'charged_off')::double as charge_offs
        from marts.fct_loan_month group by 1
        """
    )
    conv = {r["product"]: r["charge_offs"] / r["rolls"] for r in history.iter_rows(named=True)}
    recov = ctx.sql(
        "select product, max_by(recovery_rate, months_since) as r from marts.mart_recoveries group by 1"
    )
    lgd = {p: 1.0 - r for p, r in recov.iter_rows()}
    balances = {"installment": bs["loans_installment"], "card": bs["loans_card"]}
    mortgage_loss_q = float(
        ctx.sql(
            f"""
            select (sum(charge_off_amount) - sum(recovery_amount))::double / 4 as q
            from marts.fct_loan_month
            where product = 'mortgage' and month > strftime(date '{cfg.calendar.as_of}' - interval 12 month, '%Y-%m')
            """
        )["q"][0]
    )
    w = cfg.capital.risk_weights
    other = bs["total_assets"] - (
        bs["cash"]
        + bs["securities"]
        + bs["loans_installment"]
        + bs["loans_card"]
        + bs["loans_mortgage"]
        + bs["allowance"]
    )
    rwa = (
        w["cash"] * bs["cash"]
        + w["securities"] * bs["securities"]
        + w["mortgage"] * bs["loans_mortgage"]
        + w["installment"] * bs["loans_installment"]
        + w["card"] * bs["loans_card"]
        + w["other_assets"] * max(other, 0.0)
    )
    equity = bs["total_equity"]
    ratio0 = equity / rwa
    income = _floats(
        ctx.sql(
            f"""
            select sum(noninterest_income)::double as nonii, sum(noninterest_expense)::double as nonie
            from marts.mart_income_statement_monthly
            where month > strftime(date '{cfg.calendar.as_of}' - interval 12 month, '%Y-%m')
            """
        ).row(0, named=True)
    )
    ppnr_quarter = (base_nii + income["nonii"] - income["nonie"]) / 4
    m.put("f08.ppnr_quarter", ppnr_quarter, "usdm", **gen)
    m.put("f08.capital_ratio_start", ratio0, "pct1", **gen)
    m.put("f08.rwa", rwa, "usdm", **gen)
    u0 = float(macro_now["unemployment_rate"])
    m.put("f08.unemployment_start", u0, "float1", **gen)

    path_rows: list[dict[str, Any]] = []
    summary: list[list[Scalar]] = []
    central_paths: dict[str, np.ndarray] = {}
    outcomes: dict[str, tuple[float, float]] = {}  # scenario: (lowest ratio, ratio at the end)
    frb: dict[str, Any] = {
        "backend": "real:frb_scenarios",
        "population": "The Federal Reserve Board's 2026 supervisory scenarios, applied to Harborline",
        "source": "marts.mart_scenarios and ledger_stress.link",
    }
    for key, name in SCENARIOS.items():
        path = scen.filter(pl.col("scenario").is_in([key, "historic"]))
        du, dh = scenario_changes(path, JUMP_OFF, quarters)
        # The scenario's short rate moves net interest income through the same repricing gap.
        short = path.sort("quarter")
        start_rate = float(short.filter(pl.col("quarter") == JUMP_OFF)["treasury_3m"][0])
        rate_path = short.filter(pl.col("quarter").is_in(quarters)).sort("quarter")["treasury_3m"].to_numpy()
        ppnr = np.array(
            [ppnr_quarter + nii_change(positions, (r - start_rate) * 100)["total"] / 4 for r in rate_path]
        )
        loss_draws = np.zeros((2000, n_q))
        roll_q: dict[str, dict[str, np.ndarray]] = {}
        for product in UNSECURED:
            proj = project(float(h0[product]), du, dh, fit, draws=2000, seed=cfg.seed % 10_000)
            q_roll = {k: 1 - (1 - proj[k]) ** 3 for k in ("central", "low", "high")}
            roll_q[product] = q_roll
            draws_q = 1 - (1 - proj["draws"]) ** 3
            # Losses follow rolls by about a quarter: a loan charges off at 120 days past due.
            lagged = np.column_stack([np.full(draws_q.shape[0], 1 - (1 - h0[product]) ** 3), draws_q[:, :-1]])
            loss_draws += lagged * conv[product] * lgd[product] * balances[product]
        loss_draws += mortgage_loss_q
        cum = np.cumsum(loss_draws, axis=1)
        loss_c, loss_lo, loss_hi = (np.quantile(loss_draws, q, axis=0) for q in (0.5, 0.05, 0.95))
        cum_c, cum_lo, cum_hi = (np.quantile(cum, q, axis=0) for q in (0.5, 0.05, 0.95))
        cap = (equity + np.cumsum(ppnr) - cum) / rwa
        cap_c, cap_lo, cap_hi = (np.quantile(cap, q, axis=0) for q in (0.5, 0.05, 0.95))
        unsecured_bal = sum(balances.values())
        combined = {
            k: sum(roll_q[p][k] * balances[p] for p in UNSECURED) / unsecured_bal
            for k in ("central", "low", "high")
        }
        central_paths[key] = combined["central"]
        for i, quarter in enumerate(quarters):
            path_rows.append(
                {
                    "scenario": name,
                    "step": i + 1,
                    "scenario_quarter": quarter,
                    "unemployment": u0 + float(du[i]),
                    "roll_rate": float(combined["central"][i]),
                    "roll_low": float(combined["low"][i]),
                    "roll_high": float(combined["high"][i]),
                    "loss": float(loss_c[i]),
                    "loss_low": float(loss_lo[i]),
                    "loss_high": float(loss_hi[i]),
                    "cumulative_loss": float(cum_c[i]),
                    "cumulative_low": float(cum_lo[i]),
                    "cumulative_high": float(cum_hi[i]),
                    "ppnr": float(ppnr[i]),
                    "capital_ratio": float(cap_c[i]),
                    "capital_low": float(cap_lo[i]),
                    "capital_high": float(cap_hi[i]),
                }
            )
        loans = bs["loans_installment"] + bs["loans_card"] + bs["loans_mortgage"]
        summary.append(
            [
                name,
                u0 + float(du.max()),
                float(cum_c[-1]),
                float(cum_lo[-1]),
                float(cum_hi[-1]),
                float(cum_c[-1]) / loans,
                float(min(ratio0, cap_c.min())),
                float(min(ratio0, cap_lo.min())),
                float(cap_c[-1]),
            ]
        )
        outcomes[key] = (float(min(ratio0, cap_c.min())), float(cap_c[-1]))
        tag = "base" if key == "baseline" else "severe"
        m.put(f"f08.{tag}_loss", float(cum_c[-1]), "usdm", **frb)
        m.put(f"f08.{tag}_loss_low", float(cum_lo[-1]), "usdm", **frb)
        m.put(f"f08.{tag}_loss_high", float(cum_hi[-1]), "usdm", **frb)
        m.put(f"f08.{tag}_loss_rate", float(cum_c[-1]) / loans, "pct1", **frb)
        m.put(f"f08.{tag}_capital_trough", float(min(ratio0, cap_c.min())), "pct1", **frb)
        m.put(f"f08.{tag}_capital_trough_low", float(min(ratio0, cap_lo.min())), "pct1", **frb)
        m.put(f"f08.{tag}_capital_end", float(cap_c[-1]), "pct1", **frb)
        m.put(f"f08.{tag}_peak_loss_quarter", float(loss_c.max()), "usdm", **frb)
        m.put(f"f08.{tag}_ppnr_low", float(ppnr.min()), "usdm", **frb)
        m.put(f"f08.{tag}_peak_unemployment", u0 + float(du.max()), "float1", **frb)
    paths = pl.DataFrame(path_rows)
    ctx.save("stress_paths", paths)
    monotone = bool(np.all(central_paths["severely_adverse"] >= central_paths["baseline"] - 1e-12))
    m.put("f08.monotone", "yes" if monotone else "no", "text", **frb)
    m.put("f08.quarters", n_q, "int", **frb)
    m.put("f08.scenario_year", quarters[0][:4], "text", **frb)
    m.put("f08.first_quarter", quarters[0], "text", **frb)
    m.put("f08.last_quarter", quarters[-1], "text", **frb)
    m.put_table(
        "f08.scenario_table",
        [
            "Scenario",
            "Peak unemployment, bank",
            f"Losses over {n_q} quarters",
            "Low",
            "High",
            "Share of loans",
            "Capital ratio at its lowest",
            "Low",
            f"Capital ratio after {n_q} quarters",
        ],
        ["text", "float1", "usdm", "usdm", "usdm", "pct1", "pct1", "pct1", "pct1"],
        summary,
        **frb,
    )
    severe = summary[1]
    loss_peak_severe = max(r["loss"] for r in path_rows if r["scenario"] == SCENARIOS["severely_adverse"])
    ppnr_severe = min(r["ppnr"] for r in path_rows if r["scenario"] == SCENARIOS["severely_adverse"])
    m.put_figure(
        "f08.fig_roll",
        "Unsecured loans rolling into delinquency each quarter, along the 2026 scenarios",
        f"Under the severely adverse scenario, the bank's unemployment peaks at {format_value(severe[1], 'float1')} "
        f"and the quarterly roll into delinquency rises with it; the band is the link's uncertainty. These are "
        "illustrative projections on a fictional bank in the shape of the supervisory exercise, not the exercise.",
        data="f08/stress_paths.parquet",
        **frb,
    )
    m.put_figure(
        "f08.fig_capital",
        "The capital ratio along each scenario",
        f"The ratio starts at {format_value(ratio0, 'pct1')}. Severely adverse losses peak at "
        f"{format_value(float(loss_peak_severe), 'usdm')} a quarter, while pre provision revenue, held at its last "
        f"twelve months of {format_value(ppnr_quarter, 'usdm')} a quarter and moved by the scenario's short rate, "
        f"falls no lower than {format_value(float(ppnr_severe), 'usdm')}, so "
        f"the ratio ends the {n_q} quarters at {format_value(outcomes['severely_adverse'][1], 'pct1')}"
        + (
            " and never falls below where it started. "
            if outcomes["severely_adverse"][0] >= ratio0 - 1e-12
            else f" after falling to {format_value(outcomes['severely_adverse'][0], 'pct1')}. "
        )
        + "No tax, dividends or balance sheet growth; illustrative projections on a fictional bank in the shape of the "
        "supervisory exercise, not the exercise.",
        data="f08/stress_paths.parquet",
        **frb,
    )

    # ---- Liquidity ---------------------------------------------------------------------
    rates = cfg.liquidity.outflow_rates
    hqla = bs["cash"] + bs["securities"] * (1 - cfg.liquidity.hqla_haircut)
    outflows = (
        bs["deposits_checking"] * rates["checking"]
        + bs["deposits_savings"] * rates["savings"]
        + bs["deposits_time"] * rates["time"]
    )
    holders = ctx.sql(
        f"""
        select greatest(checking_balance, 0)::double + greatest(other_balance, 0)::double as balance
        from marts.mart_customer_month where month = '{as_of}'
        """
    )["balance"].to_numpy()
    top_n = max(1, int(round(0.01 * holders.size)))
    top1 = float(np.sort(holders)[::-1][:top_n].sum())
    concentrated = outflows + float(top1) * (1 - rates["checking"])
    m.put("f08.hqla", hqla, "usdm", **gen)
    m.put("f08.outflows", outflows, "usdm", **gen)
    m.put("f08.lcr", hqla / outflows, "pct0", **gen)
    m.put("f08.lcr_concentration", hqla / concentrated, "pct0", **gen)
    m.put("f08.top1_balances", float(top1), "usdm", **gen)
    m.put_table(
        "f08.liquidity",
        ["Line", "Amount"],
        ["text", "usdm"],
        [
            ["Cash", bs["cash"]],
            ["Securities, after the haircut", bs["securities"] * (1 - cfg.liquidity.hqla_haircut)],
            ["High quality liquid assets", hqla],
            [f"Checking outflow at {rates['checking']:.0%}", bs["deposits_checking"] * rates["checking"]],
            [f"Savings outflow at {rates['savings']:.0%}", bs["deposits_savings"] * rates["savings"]],
            [f"Time deposit outflow at {rates['time']:.0%}", bs["deposits_time"] * rates["time"]],
            ["Thirty day net outflows", outflows],
            ["If the largest 1% of depositors also leave in full", concentrated],
        ],
        **gen,
    )


SPEC = FunctionSpec(
    code="f08",
    slug="treasury",
    title="Treasury and stress testing",
    question="What does a rate move do to net interest income, what would the 2026 supervisory scenarios do to losses and capital, and how long would liquid assets last?",
    run=run,
)
