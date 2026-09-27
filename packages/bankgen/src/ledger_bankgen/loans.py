"""The loan book: applications, originations and monthly performance with a known default process.

Installment loans are Harborline's direct consumer lending product, launched at
the start of the window, so every installment vintage is observed from month one.
Cards and mortgages carry a seasoned back book. Each month every open loan moves
through current, 30, 60, 90 and 120 days past due, cure, prepayment, maturity or
charge off, with the monthly probability of first missing a payment set by

    logit(h) = intercept + beta_risk * z + beta_macro * (unemployment - 4.0)
               + vintage_effect * loose_vintage + seasoning(months on book)

where z is each customer's latent risk. z never leaves the truth tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import polars as pl

from ledger_bankgen.params import GeneratorParams
from ledger_bankgen.timeline import Timeline

STATES = (
    "current",
    "dpd30",
    "dpd60",
    "dpd90",
    "dpd120",
    "dpd150",
    "dpd180",
    "charged_off",
    "paid_off",
    "matured",
)
C, D30, D60, D90, D120, D150, D180, CO, PO, MAT = range(10)
PURPOSES = ("debt_consolidation", "auto", "home_improvement", "major_purchase", "other")
CHANNELS = ("branch", "digital", "partner")


def _sigmoid(x: np.ndarray) -> np.ndarray:
    out: np.ndarray = 1.0 / (1.0 + np.exp(-x))
    return out


def seasoning(mob: np.ndarray, peak: int, amplitude: float) -> np.ndarray:
    ratio = np.maximum(mob, 0) / peak
    out: np.ndarray = amplitude * (ratio * np.exp(1.0 - ratio)) - 0.5 * amplitude
    return out


def quarter_label(day: date) -> str:
    return f"{day.year}Q{(day.month - 1) // 3 + 1}"


@dataclass
class LoanBook:
    applications: pl.DataFrame
    loans: pl.DataFrame
    performance: pl.DataFrame
    events: pl.DataFrame
    truth: pl.DataFrame
    mortgage_applications: pl.DataFrame


def _annuity(principal: np.ndarray, annual_rate: np.ndarray, term: np.ndarray) -> np.ndarray:
    r = annual_rate / 12.0
    out: np.ndarray = np.where(r > 0, principal * r / (1 - (1 + r) ** (-term)), principal / term)
    return out


def _applications(
    customers: pl.DataFrame,
    params: GeneratorParams,
    timeline: Timeline,
    macro: pl.DataFrame,
    rng: np.random.Generator,
) -> pl.DataFrame:
    z_all = customers["latent_risk"].to_numpy()
    income_all = customers["annual_income"].to_numpy()
    open_all = np.array(customers["open_date"].to_list(), dtype="datetime64[D]")
    birth_all = customers["birth_year"].to_numpy()
    county_all = customers["county_fips"].to_list()
    policy = macro["policy_rate"].to_numpy()
    frames: list[dict[str, object]] = []
    app_seq = 0
    for m, month in enumerate(timeline.months):
        growth = 0.75 + 0.5 * m / max(1, len(timeline) - 1)
        count = int(rng.poisson(params.applications_per_month * growth))
        month_end = np.datetime64(month + timedelta(days=27))
        eligible = np.flatnonzero(open_all <= month_end)
        who = rng.choice(eligible, size=count, replace=True)
        z = z_all[who]
        noise = rng.normal(0, 1, (8, count))
        bureau = np.clip(np.round(702 - 58 * z + 26 * noise[0]), 480, 850)
        dti = np.clip(0.29 + 0.075 * z + 0.085 * noise[1], 0.02, 0.78)
        util = np.clip(_sigmoid(-0.35 + 0.95 * z + 0.75 * noise[2]), 0.0, 1.25)
        delinq = rng.poisson(np.exp(-1.9 + 0.85 * z))
        inquiries = rng.poisson(np.exp(0.15 + 0.38 * z))
        oldest = np.clip(np.round(np.exp(np.log(128) - 0.22 * z + 0.45 * noise[3])), 4, 520)
        tenure = np.clip(np.round(np.exp(np.log(58) - 0.18 * z + 0.9 * noise[4])), 0, 480)
        amount = np.clip(np.round(np.exp(np.log(11_500) + 0.55 * noise[5]), -2), 1_500, 50_000)
        term = rng.choice([24, 36, 48, 60, 72], size=count, p=[0.12, 0.28, 0.25, 0.25, 0.10])
        purpose = rng.choice(PURPOSES, size=count, p=[0.38, 0.27, 0.15, 0.12, 0.08])
        housing = np.where(
            rng.random(count) < np.clip(0.62 - 0.12 * z, 0.1, 0.9),
            np.where(rng.random(count) < 0.7, "mortgage", "own"),
            "rent",
        )
        channel = rng.choice(CHANNELS, size=count, p=[0.35, 0.50, 0.15])
        day = [month + timedelta(days=int(d)) for d in rng.integers(0, 28, count)]
        zip5 = [
            f"07{int(rng.integers(0, 1000)):03d}" if c else f"1{int(rng.integers(0, 10000)):04d}"
            for c in (county_all[w] for w in who)
        ]
        for i in range(count):
            app_seq += 1
            frames.append(
                {
                    "application_id": f"L{app_seq:07d}",
                    "customer_index": int(who[i]),
                    "application_date": day[i],
                    "month_index": m,
                    "bureau_score": int(bureau[i]),
                    "dti": round(float(dti[i]), 4),
                    "revolving_utilization": round(float(util[i]), 4),
                    "delinquencies_24m": int(delinq[i]),
                    "inquiries_6m": int(inquiries[i]),
                    "oldest_trade_months": int(oldest[i]),
                    "employment_months": int(tenure[i]),
                    "annual_income": float(income_all[who[i]]),
                    "loan_amount": float(amount[i]),
                    "term_months": int(term[i]),
                    "purpose": str(purpose[i]),
                    "housing_status": str(housing[i]),
                    "channel": str(channel[i]),
                    "applicant_age": int(month.year - birth_all[who[i]]),
                    "applicant_zip5": zip5[i],
                    "county_fips": county_all[who[i]],
                    "policy_rate": float(policy[m]),
                }
            )
    return pl.DataFrame(frames)


def _decide(apps: pl.DataFrame, params: GeneratorParams, rng: np.random.Generator) -> pl.DataFrame:
    """Harborline's historical approval policy, which the new scorecard replaces.

    A legacy score from the bureau score, debt to income and job tenure, with a
    cutoff that was loosened for applications in the loose vintages. The loosening
    is the story behind the vintage effect the pipeline has to recover.
    """
    loose = set(params.default.loose_vintages)
    quarter = [quarter_label(d) for d in apps["application_date"].to_list()]
    legacy = (
        apps["bureau_score"].to_numpy()
        - 170 * apps["dti"].to_numpy()
        + 10 * (apps["employment_months"].to_numpy() > 24)
        - 6 * apps["delinquencies_24m"].to_numpy()
    )
    cutoff = np.where(np.isin(quarter, list(loose)), 598.0, 622.0)
    approved = (legacy >= cutoff) & (apps["dti"].to_numpy() < 0.55)
    # A share of approvals are not taken up, as in any lending book.
    taken = approved & (rng.random(apps.height) < 0.86)
    tier = np.clip((apps["bureau_score"].to_numpy() - 560) // 40, 0, 7)
    rate = apps["policy_rate"].to_numpy() / 100.0 + 0.045 + (7 - tier) * 0.0125
    return apps.with_columns(
        vintage=pl.Series(quarter),
        legacy_score=pl.Series(np.round(legacy, 1)),
        decision=pl.Series(np.where(approved, "approved", "declined")),
        booked=pl.Series(taken),
        interest_rate=pl.Series(np.round(rate, 5)),
    )


def build_loan_book(
    customers: pl.DataFrame,
    params: GeneratorParams,
    timeline: Timeline,
    macro: pl.DataFrame,
    rng: np.random.Generator,
) -> LoanBook:
    apps = _decide(_applications(customers, params, timeline, macro, rng), params, rng)
    z_all = customers["latent_risk"].to_numpy()
    income_all = customers["annual_income"].to_numpy()
    open_all = customers["open_date"].to_list()
    unemployment = macro["unemployment_rate"].to_numpy()
    n_months = len(timeline)

    booked = apps.filter(pl.col("booked"))
    inst = {
        "loan_id": [f"N{i:07d}" for i in range(1, booked.height + 1)],
        "product": ["installment"] * booked.height,
        "customer_index": booked["customer_index"].to_numpy(),
        "application_id": booked["application_id"].to_list(),
        "origination_date": booked["application_date"].to_list(),
        "origination_month": booked["month_index"].to_numpy(),
        "principal": booked["loan_amount"].to_numpy(),
        "interest_rate": booked["interest_rate"].to_numpy(),
        "term_months": booked["term_months"].to_numpy(),
        "vintage": booked["vintage"].to_list(),
        "credit_limit": np.zeros(booked.height),
    }

    # Cards: a seasoned book for existing customers and new issuance for new ones.
    n_cust = customers.height
    card_holder = rng.random(n_cust) < params.card_share
    card_idx = np.flatnonzero(card_holder)
    card_open = []
    card_month = []
    for i in card_idx:
        opened = open_all[i]
        if opened < timeline.months[0]:
            card_open.append(opened + timedelta(days=int(rng.integers(0, 400))))
        else:
            card_open.append(opened + timedelta(days=int(rng.integers(0, 60))))
        mi = -1
        for k, mm in enumerate(timeline.months):
            if card_open[-1] >= mm:
                mi = k
        card_month.append(mi if card_open[-1] >= timeline.months[0] else -1)
    card_month_arr = np.array(card_month)
    keep = card_month_arr < n_months
    card_idx = card_idx[keep]
    card_open = [c for c, k in zip(card_open, keep, strict=True) if k]
    card_month_arr = card_month_arr[keep]
    z_card = z_all[card_idx]
    limits = np.clip(
        np.round(
            income_all[card_idx] * np.exp(-1.65 - 0.25 * z_card + 0.3 * rng.normal(0, 1, len(card_idx))), -2
        ),
        500,
        40_000,
    )
    card_rate = np.round(0.205 + 0.03 * np.clip(z_card, -2, 2) + rng.normal(0, 0.01, len(card_idx)), 4)
    cards = {
        "loan_id": [f"K{i:07d}" for i in range(1, len(card_idx) + 1)],
        "product": ["card"] * len(card_idx),
        "customer_index": card_idx,
        "application_id": [None] * len(card_idx),
        "origination_date": card_open,
        "origination_month": card_month_arr,
        "principal": np.zeros(len(card_idx)),
        "interest_rate": card_rate,
        "term_months": np.zeros(len(card_idx), dtype=int),
        "vintage": [quarter_label(x) for x in card_open],
        "credit_limit": limits,
    }

    # Mortgages: a seasoned back book plus originations in the window.
    mort_holder = np.flatnonzero(rng.random(n_cust) < params.mortgage_share)
    back = mort_holder[: int(len(mort_holder) * 0.62)]
    new = mort_holder[int(len(mort_holder) * 0.62) :]
    back_orig = [
        date(int(rng.integers(2012, 2023)), int(rng.integers(1, 13)), int(rng.integers(1, 28))) for _ in back
    ]
    new_month = rng.integers(0, n_months, len(new))
    new_orig = [timeline.months[m] + timedelta(days=int(rng.integers(0, 27))) for m in new_month]
    m_idx = np.concatenate([back, new])
    m_orig = back_orig + new_orig
    m_month = np.concatenate([np.full(len(back), -1), new_month])
    m_principal = np.round(
        np.clip(income_all[m_idx] * rng.uniform(2.6, 4.2, len(m_idx)), 90_000, 1_100_000), -3
    )
    vintage_rate = np.array(
        [
            {
                2012: 3.7,
                2013: 4.1,
                2014: 4.2,
                2015: 3.9,
                2016: 3.7,
                2017: 4.0,
                2018: 4.5,
                2019: 4.0,
                2020: 3.1,
                2021: 3.0,
                2022: 5.3,
            }.get(o.year, 6.6)
            for o in m_orig
        ]
    )
    m_rate = np.round((vintage_rate + rng.normal(0, 0.25, len(m_idx))) / 100.0, 5)
    mortgages = {
        "loan_id": [f"M{i:07d}" for i in range(1, len(m_idx) + 1)],
        "product": ["mortgage"] * len(m_idx),
        "customer_index": m_idx,
        "application_id": [None] * len(m_idx),
        "origination_date": m_orig,
        "origination_month": m_month,
        "principal": m_principal,
        "interest_rate": m_rate,
        "term_months": np.full(len(m_idx), 360),
        "vintage": [quarter_label(x) for x in m_orig],
        "credit_limit": np.zeros(len(m_idx)),
    }

    loans = pl.concat(
        [
            pl.DataFrame(inst),
            pl.DataFrame(cards),
            pl.DataFrame(mortgages),
        ],
        how="vertical_relaxed",
    ).with_columns(pl.col("origination_date").cast(pl.Date))

    perf, events = _simulate(loans, customers, params, timeline, unemployment, rng)
    truth = loans.select("loan_id", "customer_index").with_columns(
        latent_risk=pl.Series(np.round(z_all[loans["customer_index"].to_numpy()], 4))
    )
    mortgage_apps = _mortgage_applications(customers, loans, params, timeline, rng)
    customer_ids = customers["customer_id"].to_numpy()
    loans = loans.with_columns(customer_id=pl.Series(customer_ids[loans["customer_index"].to_numpy()])).drop(
        "customer_index"
    )
    apps = apps.with_columns(customer_id=pl.Series(customer_ids[apps["customer_index"].to_numpy()])).drop(
        "customer_index"
    )
    truth = truth.with_columns(customer_id=pl.Series(customer_ids[truth["customer_index"].to_numpy()])).drop(
        "customer_index"
    )
    return LoanBook(apps, loans, perf, events, truth, mortgage_apps)


def _simulate(
    loans: pl.DataFrame,
    customers: pl.DataFrame,
    params: GeneratorParams,
    timeline: Timeline,
    unemployment: np.ndarray,
    rng: np.random.Generator,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Walk every loan month by month. Returns the monthly performance and the loan events."""
    d = params.default
    n = loans.height
    n_months = len(timeline)
    product = loans["product"].to_numpy()
    is_inst = product == "installment"
    is_card = product == "card"
    is_mort = product == "mortgage"
    z = customers["latent_risk"].to_numpy()[loans["customer_index"].to_numpy()]
    rate = loans["interest_rate"].to_numpy()
    term = loans["term_months"].to_numpy()
    limit = loans["credit_limit"].to_numpy()
    orig_month = loans["origination_month"].to_numpy()
    orig_dates = loans["origination_date"].to_list()
    vintage = np.array(loans["vintage"].to_list())
    loose = np.isin(vintage, list(d.loose_vintages)) & is_inst

    # Months on book at the window start for the seasoned books.
    start = timeline.months[0]
    mob0 = np.array([max(0, (start.year - o.year) * 12 + start.month - o.month) for o in orig_dates])
    mob0 = np.where(orig_month >= 0, 0, mob0)

    principal = loans["principal"].to_numpy().astype(float)
    payment = np.where(is_card, 0.0, _annuity(principal, rate, np.maximum(term, 1)))
    balance = principal.copy()
    # Seasoned mortgages start amortised.
    r = rate / 12.0
    seasoned = is_mort & (orig_month < 0)
    k = mob0.astype(float)
    balance = np.where(
        seasoned,
        principal * ((1 + r) ** term - (1 + r) ** k) / np.maximum((1 + r) ** term - 1, 1e-9),
        balance,
    )
    utilization0 = np.clip(0.28 + 0.12 * z + rng.normal(0, 0.15, n), 0.02, 0.95)
    balance = np.where(is_card & (orig_month < 0), np.round(limit * utilization0, 2), balance)
    balance = np.where(is_card & (orig_month >= 0), 0.0, balance)
    balance = np.round(balance, 2)

    state = np.full(n, C, dtype=np.int8)
    active = orig_month < 0
    ever_d90 = np.zeros(n, dtype=bool)
    first_d90_month = np.full(n, -1)
    chargeoff_month = np.full(n, -1)
    chargeoff_amount = np.zeros(n)
    recovery_share = np.clip(rng.beta(2.0, 7.0, n) * (d.recovery_share_24m / (2.0 / 9.0)), 0, 0.95)
    recovery_share = np.where(is_mort, np.clip(rng.beta(8, 2, n), 0.5, 0.98), recovery_share)

    intercept = np.where(is_inst, d.intercept, np.where(is_card, d.intercept + 0.55, d.intercept - 2.6))
    perf_rows: list[pl.DataFrame] = []
    event_rows: list[pl.DataFrame] = []

    for m in range(n_months):
        # Originate this month's loans.
        new = orig_month == m
        active = active | new
        mob = np.where(orig_month >= 0, m - orig_month, mob0 + m)
        live = active & (state < CO)
        opening_balance = balance.copy()
        opening_state = state.copy()

        u = unemployment[m]
        logit = (
            intercept
            + d.beta_risk * z
            + d.beta_macro * (u - 4.0)
            + d.vintage_effect * loose
            + seasoning(mob, d.seasoning_peak_month, d.seasoning_amplitude)
        )
        hazard = _sigmoid(logit)
        draw = rng.random(n)
        roll_mult = np.exp(d.risk_on_roll * z) * (1.0 + 0.04 * max(0.0, u - 4.0))
        cure_mult = np.exp(-0.25 * z)

        new_state = state.copy()
        payments_made = np.zeros(n)
        # Current loans. New originations cannot miss a payment in their first month.
        cur = live & (state == C) & ~new
        prepay = np.where(is_card, 0.0, d.prepay_monthly * (1.0 + 0.4 * is_mort))
        miss = cur & (draw < hazard)
        payoff = cur & ~miss & (draw < hazard + prepay)
        stay = cur & ~miss & ~payoff
        new_state[miss] = D30
        new_state[payoff] = PO
        payments_made[stay] = 1.0
        # Delinquent loans: cure, roll or hold.
        for s_from, s_to, p_roll, p_cure in (
            (D30, D60, d.roll_30_to_60, d.cure_from_30),
            (D60, D90, d.roll_60_to_90, d.cure_from_60),
            (D90, D120, d.roll_90_to_120, d.cure_from_90),
            (D120, D150, 0.85, 0.05),
            (D150, D180, 0.9, 0.03),
        ):
            here = live & (state == s_from)
            pc = np.clip(p_cure * cure_mult, 0, 0.9)
            pr = np.clip(p_roll * roll_mult, 0, 0.97 - pc)
            cure = here & (draw < pc)
            roll = here & ~cure & (draw < pc + pr)
            hold = here & ~cure & ~roll
            new_state[cure] = C
            new_state[roll] = s_to
            arrears = s_from - C + 1
            payments_made[cure] = arrears
            payments_made[hold] = 1.0
        # Charge off policy: 120 days for installment, 180 for cards and mortgages.
        co = live & (((new_state == D120) & is_inst) | ((new_state == D180) & ~is_inst))
        newly_d90 = live & (new_state == D90) & ~ever_d90
        first_d90_month[newly_d90] = m
        ever_d90 |= new_state >= D90

        # Balances.
        interest_due = np.round(opening_balance * rate / 12.0, 2)
        card_purchases = np.where(
            is_card & live & (state == C),
            np.round(
                np.minimum(np.maximum(limit - opening_balance, 0), limit * rng.uniform(0.03, 0.14, n)), 2
            ),
            0.0,
        )
        card_purchases = np.where(
            new & is_card, np.round(limit * rng.uniform(0.05, 0.3, n), 2), card_purchases
        )
        card_min = np.maximum(25.0, 0.03 * opening_balance)
        card_pay_current = np.round(
            np.minimum(
                opening_balance + interest_due,
                np.maximum(card_min, opening_balance * rng.uniform(0.04, 0.6, n)),
            ),
            2,
        )
        sched = np.where(is_card, card_pay_current, payment)
        paid = np.round(np.minimum(sched * payments_made, opening_balance + interest_due), 2)
        paid = np.where(payoff, opening_balance + interest_due, paid)
        paid = np.where(new, 0.0, paid)
        # Card interest accrues on revolving balances; installment and mortgage interest is part of the payment.
        card_interest = np.where(is_card & live & ~new, interest_due, 0.0)
        interest_paid = np.where(
            is_card,
            0.0,
            np.minimum(
                paid,
                np.where(payments_made > 0, interest_due * payments_made, 0)
                + np.where(payoff, interest_due, 0),
            ),
        )
        interest_paid = np.round(np.minimum(interest_paid, paid), 2)
        principal_paid = np.round(paid - interest_paid, 2)
        closing = np.where(
            is_card,
            opening_balance + card_purchases + card_interest - paid,
            opening_balance - principal_paid,
        )
        closing = np.where(live, np.round(np.maximum(closing, 0.0), 2), opening_balance)
        # Maturity: an installment or mortgage that is paid down closes.
        matured = live & ~is_card & (closing <= 0.5) & (new_state == C)
        new_state[matured] = MAT
        closing = np.where(matured, 0.0, closing)
        closing = np.where(payoff, 0.0, closing)
        co_amount = np.where(co, closing, 0.0)
        chargeoff_month[co] = m
        chargeoff_amount[co] = co_amount[co]
        new_state[co] = CO
        closing = np.where(co, 0.0, closing)

        # Recoveries after charge off, front loaded over 24 months.
        since = m - chargeoff_month
        in_rec = (chargeoff_month >= 0) & (since >= 1) & (since <= 24)
        weights = np.where(in_rec, 0.12 * (0.88 ** (since - 1)), 0.0) / (1 - 0.88**24)
        recovery = np.round(np.where(in_rec, chargeoff_amount * recovery_share * weights, 0.0), 2)

        month_label = timeline.labels[m]
        emit = live | (recovery > 0)
        idx = np.flatnonzero(emit)
        perf_rows.append(
            pl.DataFrame(
                {
                    "loan_index": idx.astype(np.int32),
                    "month": [month_label] * len(idx),
                    "months_on_book": mob[idx].astype(np.int32),
                    "state_open": np.array(STATES)[opening_state[idx]],
                    "state": np.array(STATES)[new_state[idx]],
                    "opening_balance": opening_balance[idx],
                    "closing_balance": closing[idx],
                    "scheduled_payment": np.round(sched[idx], 2),
                    "amount_paid": paid[idx],
                    "interest_paid": np.where(
                        is_card[idx], np.minimum(paid[idx], card_interest[idx]), interest_paid[idx]
                    ),
                    "card_purchases": card_purchases[idx],
                    "card_interest": card_interest[idx],
                    "charge_off_amount": co_amount[idx],
                    "recovery_amount": recovery[idx],
                }
            )
        )
        # Loan events feed the general ledger. Payment day is spread through the month.
        month_start = timeline.months[m]
        ev = []
        disb = np.flatnonzero(new & ~is_card)
        if len(disb):
            ev.append(("DISBURSEMENT", disb, principal[disb]))
        payers = np.flatnonzero(live & (paid > 0))
        if len(payers):
            ev.append(
                ("PAYMENT_PRINCIPAL", payers, np.where(is_card[payers], paid[payers], principal_paid[payers]))
            )
            ip = payers[~is_card[payers] & (interest_paid[payers] > 0)]
            if len(ip):
                ev.append(("PAYMENT_INTEREST", ip, interest_paid[ip]))
        cp = np.flatnonzero(card_purchases > 0)
        if len(cp):
            ev.append(("CARD_PURCHASES", cp, card_purchases[cp]))
        ci = np.flatnonzero(card_interest > 0)
        if len(ci):
            ev.append(("CARD_INTEREST", ci, card_interest[ci]))
        coi = np.flatnonzero(co)
        if len(coi):
            ev.append(("CHARGE_OFF", coi, co_amount[coi]))
        rec = np.flatnonzero(recovery > 0)
        if len(rec):
            ev.append(("RECOVERY", rec, recovery[rec]))
        for kind, which, amounts in ev:
            day_offset = (
                rng.integers(0, 27, len(which))
                if kind not in {"CARD_INTEREST", "CHARGE_OFF"}
                else np.full(len(which), 27)
            )
            event_rows.append(
                pl.DataFrame(
                    {
                        "loan_index": which.astype(np.int32),
                        "month": [month_label] * len(which),
                        "event_type": [kind] * len(which),
                        "amount": np.round(amounts, 2),
                        "posted_date": [month_start + timedelta(days=int(o)) for o in day_offset],
                        # A payoff is funded from outside the bank (a refinance or a sale), not from checking.
                        "is_payoff": payoff[which]
                        if kind.startswith("PAYMENT")
                        else np.zeros(len(which), dtype=bool),
                    }
                )
            )
        balance = closing
        state = new_state

    perf = pl.concat(perf_rows)
    events = pl.concat(event_rows).with_columns(pl.col("posted_date").cast(pl.Date))
    id_map = pl.DataFrame(
        {"loan_index": np.arange(loans.height, dtype=np.int32), "loan_id": loans["loan_id"]}
    )
    perf = perf.join(id_map, on="loan_index", how="left").drop("loan_index")
    events = events.join(id_map, on="loan_index", how="left").drop("loan_index")
    return perf, events


def _mortgage_applications(
    customers: pl.DataFrame,
    loans: pl.DataFrame,
    params: GeneratorParams,
    timeline: Timeline,
    rng: np.random.Generator,
) -> pl.DataFrame:
    """HMDA style application records for mortgages applied for in the window.

    Race, ethnicity and sex exist here and nowhere else, because the Home Mortgage
    Disclosure Act requires a lender to collect them. They are assigned
    independently of every credit attribute, so any disparity in this table is
    noise, and no model ever joins to this table.
    """
    originated = loans.filter((pl.col("product") == "mortgage") & (pl.col("origination_month") >= 0))
    n_orig = originated.height
    n_declined = int(n_orig * 0.28)
    n_withdrawn = int(n_orig * 0.12)
    total = n_orig + n_declined + n_withdrawn
    action = ["originated"] * n_orig + ["denied"] * n_declined + ["withdrawn"] * n_withdrawn
    months = np.concatenate(
        [originated["origination_month"].to_numpy(), rng.integers(0, len(timeline), n_declined + n_withdrawn)]
    )
    race = rng.choice(
        [
            "White",
            "Black or African American",
            "Asian",
            "Joint",
            "Race not available",
            "Two or more minority races",
        ],
        size=total,
        p=[0.56, 0.11, 0.12, 0.03, 0.16, 0.02],
    )
    ethnicity = rng.choice(
        ["Not Hispanic or Latino", "Hispanic or Latino", "Joint", "Ethnicity not available"],
        size=total,
        p=[0.68, 0.14, 0.03, 0.15],
    )
    sex = rng.choice(["Male", "Female", "Joint", "Sex not available"], size=total, p=[0.38, 0.24, 0.28, 0.10])
    reasons = rng.choice(
        ["Debt-to-income ratio", "Credit history", "Collateral", "Insufficient cash", "Other"],
        size=total,
        p=[0.36, 0.24, 0.18, 0.12, 0.10],
    )
    denial_reason = [str(r) if a == "denied" else None for a, r in zip(action, reasons, strict=True)]
    rng.shuffle(race)
    return pl.DataFrame(
        {
            "hmda_application_id": [f"H{i:06d}" for i in range(1, total + 1)],
            "month": [timeline.labels[int(m)] for m in months],
            "action_taken": action,
            "derived_race": race,
            "derived_ethnicity": ethnicity,
            "derived_sex": sex,
            "denial_reason_1": pl.Series(denial_reason, dtype=pl.Utf8),
        }
    )
