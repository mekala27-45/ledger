from __future__ import annotations

from datetime import date, datetime, timedelta

import polars as pl
from hypothesis import given, settings
from hypothesis import strategies as st
from ledger_core.calendar import CensoringCalendar, add_months, month_end

AS_OF = date(2026, 8, 31)
CAL = CensoringCalendar(as_of=AS_OF, default_window_months=12, chargeback_window_days=60, cure_window_days=90)


def test_add_months_clamps_to_month_end() -> None:
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2023, 12, 15), 2) == date(2024, 2, 15)
    assert month_end(date(2025, 2, 3)) == date(2025, 2, 28)


def test_a_loan_originated_last_month_has_no_default_outcome() -> None:
    assert not CAL.default_observed(date(2026, 7, 15))
    assert CAL.default_observed(date(2025, 8, 31))
    assert not CAL.default_observed(date(2025, 9, 1))


def test_a_transaction_from_last_week_has_no_fraud_label() -> None:
    assert not CAL.fraud_label_observed(datetime(2026, 8, 24, 12, 0))
    assert CAL.fraud_label_observed(datetime(2026, 6, 1, 12, 0))


@settings(max_examples=300, deadline=None)
@given(st.dates(min_value=date(2020, 1, 1), max_value=date(2027, 12, 31)))
def test_default_window_is_never_marked_observed_before_it_elapses(origination: date) -> None:
    observed = CAL.default_observed(origination)
    assert observed == (add_months(origination, 12) <= AS_OF)
    if observed:
        assert add_months(origination, 12) <= AS_OF


@settings(max_examples=300, deadline=None)
@given(st.datetimes(min_value=datetime(2025, 1, 1), max_value=datetime(2026, 12, 31)))
def test_chargeback_window_is_never_marked_observed_early(moment: datetime) -> None:
    now = datetime(2026, 8, 31, 23, 59)
    if CAL.fraud_label_observed(moment, now):
        assert moment + timedelta(days=60) <= now


def test_vectorised_forms_agree_with_the_scalar_ones() -> None:
    days = [date(2025, 8, 1) + timedelta(days=i) for i in range(0, 60)]
    frame = pl.DataFrame({"d": days})
    vector = frame.select(CAL.default_observed_expr("d")).to_series().to_list()
    assert vector == [CAL.default_observed(d) for d in days]
    now = datetime(2026, 8, 31, 12)
    stamps = [datetime(2026, 6, 20) + timedelta(hours=6 * i) for i in range(60)]
    tframe = pl.DataFrame({"t": stamps})
    tvector = tframe.select(CAL.fraud_label_observed_expr("t", now)).to_series().to_list()
    assert tvector == [CAL.fraud_label_observed(t, now) for t in stamps]
