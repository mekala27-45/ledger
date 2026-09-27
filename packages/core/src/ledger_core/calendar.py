"""The censoring calendar.

A loan originated last month has no twelve month default outcome yet, and a card
transaction from last week has no fraud label yet. Both are right censoring, and
both are decided here and nowhere else, so no module can quietly count an
outcome that has not had time to happen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import polars as pl


def add_months(day: date, months: int) -> date:
    """Calendar month arithmetic that clamps to the last day of the target month."""
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    next_month_first = date(year + (month // 12), month % 12 + 1, 1)
    last_day = (next_month_first - timedelta(days=1)).day
    return date(year, month, min(day.day, last_day))


def month_end(day: date) -> date:
    return add_months(date(day.year, day.month, 1), 1) - timedelta(days=1)


@dataclass(frozen=True)
class CensoringCalendar:
    """Decides whether an outcome window has fully elapsed by the as of date."""

    as_of: date
    default_window_months: int = 12
    chargeback_window_days: int = 60
    cure_window_days: int = 90

    def default_window_end(self, origination: date) -> date:
        return add_months(origination, self.default_window_months)

    def default_observed(self, origination: date) -> bool:
        """The twelve month default window is observed only once it has elapsed."""
        return self.default_window_end(origination) <= self.as_of

    def label_observable_at(self, transaction_time: datetime) -> datetime:
        return transaction_time + timedelta(days=self.chargeback_window_days)

    def fraud_label_observed(self, transaction_time: datetime, now: datetime | None = None) -> bool:
        """A fraud label exists only after the chargeback window has passed."""
        reference = now or datetime.combine(self.as_of, datetime.max.time())
        return self.label_observable_at(transaction_time) <= reference

    def cure_observed(self, delinquency_date: date) -> bool:
        return delinquency_date + timedelta(days=self.cure_window_days) <= self.as_of

    # Vectorised forms used by the pipeline. Each mirrors a scalar method above and a
    # property test asserts the two agree.

    def default_observed_expr(self, origination_col: str) -> pl.Expr:
        return pl.col(origination_col).dt.offset_by(f"{self.default_window_months}mo") <= pl.lit(self.as_of)

    def fraud_label_observed_expr(self, time_col: str, now: datetime) -> pl.Expr:
        return pl.col(time_col) + pl.duration(days=self.chargeback_window_days) <= pl.lit(now)

    def cure_observed_expr(self, date_col: str) -> pl.Expr:
        return pl.col(date_col) + pl.duration(days=self.cure_window_days) <= pl.lit(self.as_of)


def calendar_from_config() -> CensoringCalendar:
    from ledger_core.config import config

    cfg = config()
    return CensoringCalendar(
        as_of=cfg.calendar.as_of,
        default_window_months=cfg.censoring.default_window_months,
        chargeback_window_days=cfg.censoring.chargeback_window_days,
        cure_window_days=cfg.censoring.cure_window_days,
    )
