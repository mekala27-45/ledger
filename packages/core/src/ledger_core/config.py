"""Typed access to config/ledger.yaml. Every stated assumption comes through here."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from ledger_core.model import StrictModel
from ledger_core.paths import paths


class BankSection(StrictModel):
    name: str
    short_name: str
    home_state: str
    footprint: list[str]


class CalendarSection(StrictModel):
    start: date
    as_of: date
    months: int


class LedgerBreak(StrictModel):
    gl_account: str
    month: str
    amount: float


class GeneratorSection(StrictModel):
    customers: int
    branches: int
    recession_months: list[str]
    ledger_break: LedgerBreak


class CensoringSection(StrictModel):
    default_window_months: int
    default_dpd: int
    cure_window_days: int
    chargeback_window_days: int


class FraudDeskSection(StrictModel):
    cost_false_decline: float
    cost_missed_fraud_handling: float
    queue_precision_floor: float
    replay_speed_seconds_per_hour: float


class ScorecardSection(StrictModel):
    base_score: int
    base_odds: float
    points_to_double_odds: float
    iv_floor: float
    correlation_ceiling: float
    min_bin_share: float
    max_fine_bins: int
    approval_cutoff_score: int
    reason_codes_returned: int


class LendingSection(StrictModel):
    lgd_installment_source: str
    cecl_horizon_months: int


class CapitalSection(StrictModel):
    risk_weights: dict[str, float]


class LiquiditySection(StrictModel):
    outflow_rates: dict[str, float]
    hqla_haircut: float


class TreasurySection(StrictModel):
    shocks_bps: list[int]
    horizon_months: int
    securities_ladder_years: float = 5.0
    stress_quarters: int = 9


class AmlSection(StrictModel):
    reporting_threshold: float
    structuring_floor: float
    structuring_window_days: int
    rapid_movement_hours: int
    mule_fan_in_min_counterparties: int
    mule_window_days: int
    cycle_max_length: int
    cycle_window_days: int


class ModelRiskSection(StrictModel):
    tiers: dict[int, str]
    psi_warning: float
    psi_breach: float


class LedgerConfig(StrictModel):
    bank: BankSection
    calendar: CalendarSection
    seed: int
    generator: GeneratorSection
    censoring: CensoringSection
    fraud_desk: FraudDeskSection
    scorecard: ScorecardSection
    lending: LendingSection
    capital: CapitalSection
    liquidity: LiquiditySection
    treasury: TreasurySection
    aml: AmlSection
    model_risk: ModelRiskSection


def load_config(path: Path | None = None) -> LedgerConfig:
    source = path or paths().config
    with source.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return LedgerConfig.model_validate(raw)


@lru_cache(maxsize=1)
def config() -> LedgerConfig:
    return load_config()
