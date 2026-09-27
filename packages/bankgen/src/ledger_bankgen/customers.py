"""Customers, with only what a bank lawfully holds for its own analytics.

Age, state, county, tenure, segment, income band and channel. No names, no
addresses beyond county, no race or sex: those exist only in the HMDA style
mortgage application records, where the law requires the bank to collect them,
and are never joined to a model.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl

from ledger_bankgen.params import GeneratorParams
from ledger_bankgen.timeline import Timeline

# New Jersey counties by 2020 census population, in thousands, used only as
# sampling weights for where generated customers live.
NJ_COUNTIES: dict[str, tuple[str, int]] = {
    "34001": ("Atlantic", 275),
    "34003": ("Bergen", 955),
    "34005": ("Burlington", 461),
    "34007": ("Camden", 524),
    "34009": ("Cape May", 95),
    "34011": ("Cumberland", 154),
    "34013": ("Essex", 864),
    "34015": ("Gloucester", 302),
    "34017": ("Hudson", 724),
    "34019": ("Hunterdon", 129),
    "34021": ("Mercer", 387),
    "34023": ("Middlesex", 863),
    "34025": ("Monmouth", 644),
    "34027": ("Morris", 509),
    "34029": ("Ocean", 637),
    "34031": ("Passaic", 524),
    "34033": ("Salem", 65),
    "34035": ("Somerset", 346),
    "34037": ("Sussex", 145),
    "34039": ("Union", 575),
    "34041": ("Warren", 110),
}
BRANCH_COUNTIES = [
    "34003",
    "34003",
    "34013",
    "34017",
    "34027",
    "34031",
    "34039",
    "34023",
    "34023",
    "34025",
    "34025",
    "34035",
    "34021",
    "34029",
    "34005",
    "34007",
    "34041",
    "34037",
]
SEGMENTS = ("mass", "emerging", "affluent")
SEGMENT_WEIGHTS = (0.70, 0.20, 0.10)
SEGMENT_INCOME = {
    "mass": (np.log(62_000), 0.45),
    "emerging": (np.log(48_000), 0.40),
    "affluent": (np.log(165_000), 0.45),
}


def build_customers(params: GeneratorParams, timeline: Timeline, rng: np.random.Generator) -> pl.DataFrame:
    n = params.customers
    start = timeline.months[0]
    end = timeline.months[-1]

    existing = rng.random(n) < 0.70
    # Existing customers opened between 2004 and the window start, weighted toward recent years.
    span_days = (start - date(2004, 1, 1)).days
    back_days = (span_days * rng.beta(1.4, 1.0, n)).astype(int)
    open_existing = np.array([start - timedelta(days=int(d) + 1) for d in back_days])
    # New customers join through the window with modest growth.
    month_weights = np.linspace(0.8, 1.2, len(timeline))
    month_idx = rng.choice(len(timeline), size=n, p=month_weights / month_weights.sum())
    day_offsets = rng.integers(0, 28, n)
    open_new = np.array(
        [timeline.months[i] + timedelta(days=int(d)) for i, d in zip(month_idx, day_offsets, strict=True)]
    )
    open_date = np.where(existing, open_existing, open_new)

    segment = rng.choice(SEGMENTS, size=n, p=SEGMENT_WEIGHTS)
    age_at_asof = np.clip(np.round(rng.normal(47, 16, n)), 18, 92).astype(int)
    age_at_asof = np.where(segment == "emerging", np.clip(age_at_asof - 14, 18, 60), age_at_asof)
    birth_year = end.year - age_at_asof

    income = np.empty(n)
    for seg, (mu, sigma) in SEGMENT_INCOME.items():
        mask = segment == seg
        income[mask] = rng.lognormal(mu, sigma, mask.sum())
    income = np.round(income, -2)

    state = rng.choice(["NJ", "NY", "PA"], size=n, p=[0.80, 0.12, 0.08])
    fips = list(NJ_COUNTIES)
    weights = np.array([NJ_COUNTIES[f][1] for f in fips], dtype=float)
    county = rng.choice(fips, size=n, p=weights / weights.sum())
    county_list: list[str | None] = [
        str(c) if s == "NJ" else None for s, c in zip(state, county, strict=True)
    ]

    branch_of_county = {c: [i + 1 for i, bc in enumerate(BRANCH_COUNTIES) if bc == c] for c in fips}
    branch = np.empty(n, dtype=int)
    for i in range(n):
        options = branch_of_county.get(county_list[i] or "", [])
        branch[i] = (
            rng.choice(options) if options and rng.random() < 0.8 else rng.integers(1, params.branches + 1)
        )

    digital = rng.random(n) < np.where(age_at_asof < 40, 0.78, np.where(age_at_asof < 65, 0.55, 0.28))
    # The latent credit risk score. Truth only: never a column any model can see.
    z = (
        rng.normal(0, 1, n)
        + np.where(segment == "affluent", -0.35, 0.0)
        + np.where(segment == "emerging", 0.25, 0.0)
    )
    complaint_prone = rng.random(n) < 0.03

    return pl.DataFrame(
        {
            "customer_id": [f"C{i:06d}" for i in range(1, n + 1)],
            "open_date": open_date.astype("datetime64[D]"),
            "birth_year": birth_year,
            "state": state,
            "county_fips": pl.Series(county_list, dtype=pl.Utf8),
            "segment": segment,
            "annual_income": income,
            "home_branch": branch,
            "digital_active": digital,
            "complaint_flag": complaint_prone,
            "latent_risk": np.round(z, 4),
        }
    ).with_columns(pl.col("open_date").cast(pl.Date))
