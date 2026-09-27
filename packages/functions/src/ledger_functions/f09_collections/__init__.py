"""Function 9: collections and recovery.

Question: how many unsecured loans will charge off over the next six months, which
delinquent loans should a collector call first, and how much comes back after a charge
off?

Method: a monthly transition matrix over the delinquency buckets, estimated from the six
months before each origin and applied forward with a seasonal adjustment to the roll
into delinquency, backtested on rolling origins against naive and seasonal naive
benchmarks; the cure model's queue, ranked by balance times the probability of not
curing; and recovery curves by months since charge off, the source of the loss given
default in function 2.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import polars as pl
from ledger_core.formats import format_value
from ledger_core.manifest import Manifest, Scalar

from ledger_functions.base import Context, FunctionSpec

STATES = ("current", "30", "60", "90+", "charged_off", "paid_off")
OPEN = ("current", "30", "60", "90+")
WINDOW = 6
HORIZON = 6
UNSECURED = ("installment", "card")


def months_between(a: str, b: str) -> int:
    ay, am = (int(x) for x in a.split("-"))
    by, bm = (int(x) for x in b.split("-"))
    return (by * 12 + bm) - (ay * 12 + am)


def shift(month: str, k: int) -> str:
    y, mo = (int(x) for x in month.split("-"))
    total = y * 12 + (mo - 1) + k
    return f"{total // 12}-{total % 12 + 1:02d}"


def transition_matrix(flows: pl.DataFrame) -> np.ndarray:
    """Row normalised counts from ``bucket_open`` to ``bucket``; the two exits are absorbing."""
    idx = {s: i for i, s in enumerate(STATES)}
    counts = np.zeros((len(STATES), len(STATES)))
    for a, b, n in flows.select("from_state", "to_state", "loans").iter_rows():
        counts[idx[a], idx[b]] += n
    for s in ("charged_off", "paid_off"):
        counts[idx[s]] = 0.0
        counts[idx[s], idx[s]] = 1.0
    totals = counts.sum(axis=1, keepdims=True)
    empty = totals[:, 0] == 0
    counts[empty, idx["current"]] = 1.0
    totals[empty] = 1.0
    return counts / totals


def seasonal_factor(roll_rates: dict[str, float], before: str, calendar_month: int) -> float:
    """The roll into delinquency in this calendar month relative to all months, from history before ``before``."""
    history = {mo: r for mo, r in roll_rates.items() if mo < before}
    same = [r for mo, r in history.items() if int(mo[5:]) == calendar_month]
    if not same or not history:
        return 1.0
    return float(np.mean(same) / np.mean(list(history.values())))


def forecast(start: np.ndarray, matrix: np.ndarray, factors: list[float]) -> tuple[np.ndarray, np.ndarray]:
    """Bucket counts and charge offs for each month ahead, with the current row's roll scaled by each factor."""
    ic, i30 = STATES.index("current"), STATES.index("30")
    ico = STATES.index("charged_off")
    v = start.astype(float).copy()
    states, charge_offs = [], []
    for f in factors:
        p = matrix.copy()
        roll = min(0.99, p[ic, i30] * f)
        rest = 1.0 - p[ic, i30]
        p[ic] = p[ic] * ((1.0 - roll) / rest if rest > 0 else 1.0)
        p[ic, i30] = roll
        nxt = v @ p
        charge_offs.append(nxt[ico] - v[ico])
        v = nxt
        states.append(v.copy())
    return np.array(states), np.array(charge_offs)


def run(ctx: Context) -> None:
    m = ctx.manifest
    cfg = ctx.config
    as_of = cfg.calendar.as_of.strftime("%Y-%m")
    gen: dict[str, Any] = {
        "backend": "generated",
        "population": "Harborline installment and card loans, September 2023 to August 2026",
        "source": "marts.fct_loan_month",
    }
    flows = ctx.sql(
        f"""
        select month, bucket_open as from_state,
            case when bucket in ('paid_off', 'matured') then 'paid_off' else bucket end as to_state,
            count(*) as loans
        from marts.fct_loan_month
        where product in {UNSECURED} and bucket_open in ('current', '30', '60', '90+')
        group by 1, 2, 3
        """
    )
    months = sorted(flows["month"].unique().to_list())
    roll = (
        flows.filter(pl.col("from_state") == "current")
        .group_by("month")
        .agg((pl.col("loans").filter(pl.col("to_state") == "30").sum() / pl.col("loans").sum()).alias("rate"))
    )
    roll_rates = dict(roll.iter_rows())
    books = ctx.sql(
        f"""
        select month, bucket, count(*) as loans
        from marts.fct_loan_month where product in {UNSECURED} and bucket in ('current', '30', '60', '90+')
        group by 1, 2
        """
    )
    cohort_offs = ctx.sql(
        f"""
        -- For each origin month, loans open at its month end and the months they later charged off in.
        select o.month as origin, c.month as later
        from marts.fct_loan_month o
        join marts.fct_loan_month c on c.loan_id = o.loan_id and c.month > o.month
            and c.bucket = 'charged_off' and c.bucket_open <> 'charged_off'
        where o.product in {UNSECURED} and o.bucket in ('current', '30', '60', '90+')
        """
    )
    book_offs = dict(
        flows.filter(pl.col("to_state") == "charged_off")
        .group_by("month")
        .agg(pl.col("loans").sum())
        .iter_rows()
    )

    def start_vector(origin: str) -> np.ndarray:
        rows = dict(books.filter(pl.col("month") == origin).select("bucket", "loans").iter_rows())
        return np.array([float(rows.get(s, 0)) for s in STATES])

    def matrix_at(origin: str) -> np.ndarray:
        window = [shift(origin, -k) for k in range(WINDOW)]
        return transition_matrix(
            flows.filter(pl.col("month").is_in(window))
            .group_by("from_state", "to_state")
            .agg(pl.col("loans").sum())
        )

    rows: list[dict[str, Any]] = []
    first_origin = shift(months[0], 11)
    last_origin = shift(as_of, -HORIZON)
    origin = first_origin
    while origin <= last_origin:
        p = matrix_at(origin)
        ahead = [shift(origin, k) for k in range(1, HORIZON + 1)]
        factors = [seasonal_factor(roll_rates, shift(origin, 1), int(mo[5:])) for mo in ahead]
        _, offs = forecast(start_vector(origin), p, factors)
        _, offs_flat = forecast(start_vector(origin), p, [1.0] * HORIZON)
        actual = cohort_offs.filter((pl.col("origin") == origin) & pl.col("later").is_in(ahead)).height
        naive = sum(book_offs.get(shift(origin, -k), 0) for k in range(HORIZON))
        seasonal_naive = sum(book_offs.get(shift(origin, k - 12), 0) for k in range(1, HORIZON + 1))
        rows.append(
            {
                "origin": origin,
                "actual": float(actual),
                "forecast": float(offs.sum()),
                "forecast_unadjusted": float(offs_flat.sum()),
                "naive": float(naive),
                "seasonal_naive": float(seasonal_naive),
            }
        )
        origin = shift(origin, 1)
    backtest = pl.DataFrame(rows)
    ctx.save("backtest", backtest)

    def mape(col: str) -> float:
        a = backtest["actual"].to_numpy()
        f = backtest[col].to_numpy()
        return float(np.mean(np.abs(f - a) / a))

    def bias(col: str) -> float:
        a = backtest["actual"].to_numpy()
        f = backtest[col].to_numpy()
        return float(np.mean((f - a) / a))

    methods = [
        ("Roll rates with the seasonal adjustment", "forecast"),
        ("Roll rates without it", "forecast_unadjusted"),
        ("Naive: the last six months again", "naive"),
        ("Seasonal naive: the same months a year earlier", "seasonal_naive"),
    ]
    table: list[list[Scalar]] = [[name, mape(col), bias(col)] for name, col in methods]
    m.put_table(
        "f09.backtest_table",
        ["Method", "Mean absolute error, share of actual", "Mean error, share of actual"],
        ["text", "pct1", "spct1"],
        table,
        **gen,
    )
    best = min(methods, key=lambda t: mape(t[1]))
    m.put("f09.origins", backtest.height, "int", **gen)
    m.put("f09.first_origin", backtest["origin"][0], "text", **gen)
    m.put("f09.last_origin", backtest["origin"][-1], "text", **gen)
    m.put("f09.mape_roll", mape("forecast"), "pct1", **gen)
    m.put("f09.mape_flat", mape("forecast_unadjusted"), "pct1", **gen)
    m.put("f09.mape_naive", mape("naive"), "pct1", **gen)
    m.put("f09.mape_seasonal_naive", mape("seasonal_naive"), "pct1", **gen)
    m.put("f09.best_method", best[0], "text", **gen)
    seasonal_helps = mape("forecast") < mape("forecast_unadjusted")
    m.put_figure(
        "f09.fig_backtest",
        "Six month charge offs: forecast against what happened, by origin",
        f"Over {backtest.height} rolling origins from {backtest['origin'][0]} to {backtest['origin'][-1]}, the roll rate "
        f"forecast missed the six month charge off count by {format_value(mape('forecast'), 'pct1')} on average, "
        f"against {format_value(mape('naive'), 'pct1')} for repeating the last six months and "
        f"{format_value(mape('seasonal_naive'), 'pct1')} for the same months a year earlier. "
        + (
            "The seasonal adjustment helped."
            if seasonal_helps
            else f"The seasonal adjustment did not help ({format_value(mape('forecast_unadjusted'), 'pct1')} without "
            "it): this generator has no calendar season in its delinquency, and two years of history cannot find one."
        ),
        data="f09/backtest.parquet",
        **gen,
    )

    # The forecast from the as of month.
    p_now = matrix_at(as_of)
    ahead = [shift(as_of, k) for k in range(1, HORIZON + 1)]
    factors = [seasonal_factor(roll_rates, shift(as_of, 1), int(mo[5:])) for mo in ahead]
    use = factors if seasonal_helps else [1.0] * HORIZON
    states, offs = forecast(start_vector(as_of), p_now, use)
    fc = pl.DataFrame(
        {
            "month": ahead,
            **{f"b_{s}": states[:, i] for i, s in enumerate(STATES) if s in OPEN},
            "charge_offs": offs,
        }
    )
    ctx.save("forecast", fc)
    m.put("f09.forecast_charge_offs", float(offs.sum()), "int", **gen)
    m.put("f09.forecast_first", ahead[0], "text", **gen)
    m.put("f09.forecast_last", ahead[-1], "text", **gen)
    m.put_table(
        "f09.forecast_table",
        ["Month", "Current", "30 days", "60 days", "90 days and over", "Charge offs"],
        ["text", "int", "int", "int", "int", "int"],
        [[r[0], *[float(x) for x in r[1:]]] for r in fc.rows()],
        **gen,
    )
    m.put_figure(
        "f09.fig_forecast",
        "The next six months for the loans open today",
        f"From the {as_of} book, the roll rate chain expects about {format_value(float(offs.sum()), 'int')} charge offs "
        f"between {ahead[0]} and {ahead[-1]}, with no new loans added and the last six months' transitions held.",
        data="f09/forecast.parquet",
        **gen,
    )

    # Observed cure rates against the generator's stated ones.
    truth = json.loads((ctx.paths.raw / "truth" / "truth_parameters.json").read_text())["default"]
    stated = {"30": truth["cure_from_30"], "60": truth["cure_from_60"], "90+": truth["cure_from_90"]}
    observed = (
        flows.filter(pl.col("from_state").is_in(["30", "60", "90+"]))
        .group_by("from_state")
        .agg(
            (pl.col("loans").filter(pl.col("to_state") == "current").sum() / pl.col("loans").sum()).alias(
                "rate"
            )
        )
    )
    obs = dict(observed.iter_rows())
    m.put_table(
        "f09.cure_rates",
        ["From", "Stated monthly cure for an average loan", "Observed monthly cure"],
        ["text", "pct1", "pct1"],
        [
            [f"{b} days" if b != "90+" else "90 days and over", stated[b], obs.get(b)]
            for b in ("30", "60", "90+")
        ],
        **gen,
    )

    # The collections queue, over every product.
    owed: dict[str, Any] = {**gen, "population": f"Harborline loans past due at the end of {as_of}"}
    model = Manifest.load(ctx.paths.models_dir / "cure" / "manifest.json")
    queue = pl.read_parquet(ctx.paths.models_dir / "cure" / "queue.parquet")
    ctx.save("queue", queue)
    for key in (
        "delinquent_now",
        "queue_size",
        "queue_exposure",
        "queue_balance",
        "delinquent_balance",
        "total_exposure",
    ):
        entry = model.values[f"models.cure.{key}"]
        m.put(f"f09.{key}", entry.value, entry.fmt, **owed)
    m.put_table(
        "f09.queue_top",
        [
            "Loan",
            "Product",
            "Bucket",
            "Balance",
            "Probability of curing",
            "Balance likely lost without a call",
            "Why",
        ],
        ["text", "text", "text", "usd0", "pct1", "usd0", "text"],
        queue.head(15).rows(),
        **owed,
    )
    m.put_figure(
        "f09.fig_queue",
        "The collections queue: balance at risk times the chance of not curing",
        f"{model.text('models.cure.delinquent_now')} loans were past due at the end of {as_of}, holding "
        f"{model.text('models.cure.delinquent_balance')}. The first {model.text('models.cure.queue_size')} calls in the "
        f"queue cover {model.text('models.cure.queue_exposure')} of the {model.text('models.cure.total_exposure')} the "
        "bank expects to lose without collection, because the order is by money at risk, not by bucket.",
        data="f09/queue.parquet",
        **owed,
    )

    # Recovery curves, the source of the loss given default.
    rec = ctx.sql(
        "select product, months_since, recovery_rate from marts.mart_recoveries order by product, months_since"
    )
    ctx.save("recoveries", rec)
    at24 = dict(rec.filter(pl.col("months_since") == 24).select("product", "recovery_rate").iter_rows())
    for product, r in at24.items():
        m.put(f"f09.recovery_24_{product}", r, "pct1", **gen)
        m.put(f"f09.lgd_{product}", 1 - r, "pct1", **gen)
    m.put_figure(
        "f09.fig_recovery",
        "Cumulative recoveries after charge off",
        f"Two years after charge off, installment loans have returned {format_value(at24['installment'], 'pct1')} of the "
        f"charged off balance, cards {format_value(at24['card'], 'pct1')} and mortgages "
        f"{format_value(at24['mortgage'], 'pct1')}, where the house is collateral. One minus the installment figure is "
        "the loss given default that function 2's expected loss uses.",
        data="f09/recoveries.parquet",
        **gen,
    )


SPEC = FunctionSpec(
    code="f09",
    slug="collections",
    title="Collections and recovery",
    question="How many loans will charge off in the next six months, whom should a collector call first, and how much comes back?",
    run=run,
)
