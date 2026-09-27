"""The generated bank's thirty six months and its own macro history.

The macro path is the generator's, not the real economy's: a stated recession
quarter in spring 2025 with an emergency policy rate cut, and a slow recovery.
The stress link model in function 8 is fitted on this path and must recover the
generator's macro sensitivity before it projects anything along the Federal
Reserve's real scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import polars as pl

from ledger_bankgen.params import GeneratorParams


@dataclass(frozen=True)
class Timeline:
    months: list[date]

    @property
    def labels(self) -> list[str]:
        return [f"{m.year:04d}-{m.month:02d}" for m in self.months]

    def index_of(self, label: str) -> int:
        return self.labels.index(label)

    def __len__(self) -> int:
        return len(self.months)


def build_timeline(params: GeneratorParams) -> Timeline:
    months: list[date] = []
    year, month = params.start.year, params.start.month
    for _ in range(params.months):
        months.append(date(year, month, 1))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return Timeline(months)


def build_macro(params: GeneratorParams, timeline: Timeline, rng: np.random.Generator) -> pl.DataFrame:
    """Monthly unemployment, policy rate, ten year yield and house price growth."""
    n = len(timeline)
    labels = timeline.labels
    m = params.macro
    rec = [timeline.index_of(x) for x in params.recession_months]
    first, last = rec[0], rec[-1]

    unemployment = np.empty(n)
    unemployment[:first] = np.linspace(m.unemployment_start, m.unemployment_start + 0.3, first)
    unemployment[first : last + 1] = np.linspace(
        unemployment[first - 1] + 0.6, m.unemployment_peak, last - first + 1
    )
    unemployment[last + 1 :] = np.linspace(m.unemployment_peak - 0.2, m.unemployment_end, n - last - 1)
    unemployment = np.round(unemployment + rng.normal(0, 0.03, n), 2)

    policy = np.empty(n)
    hold = 12
    policy[:hold] = m.policy_rate_start
    policy[hold:first] = (
        np.round(np.linspace(m.policy_rate_start - 0.25, m.policy_rate_pre_shock, first - hold) * 4) / 4
    )
    shock_total = m.policy_rate_shock_bps / 100.0
    steps = np.array([0.33, 0.83, 1.0])[: last - first + 1]
    policy[first : last + 1] = m.policy_rate_pre_shock + shock_total * steps
    policy[last + 1 :] = np.maximum(
        m.policy_rate_end,
        np.round(np.linspace(policy[last] - 0.125, m.policy_rate_end, n - last - 1) * 8) / 8,
    )
    policy = np.round(policy, 2)

    term_spread = np.linspace(-0.9, 1.2, n)
    ten_year = np.round(policy + term_spread + rng.normal(0, 0.06, n), 2)

    hpi_growth = np.full(n, m.hpi_growth_normal)
    hpi_growth[first : last + 1] = m.hpi_growth_recession
    hpi_growth[last + 1 :] = np.linspace(0.0, 0.03, n - last - 1)
    hpi_index = 100.0 * np.cumprod(1 + hpi_growth / 12.0)

    return pl.DataFrame(
        {
            "month": labels,
            "month_start": timeline.months,
            "unemployment_rate": unemployment,
            "policy_rate": policy,
            "ten_year_yield": ten_year,
            "hpi_growth_annualised": np.round(hpi_growth, 4),
            "hpi_index": np.round(hpi_index, 3),
            "is_recession": [i in rec for i in range(n)],
        }
    )
