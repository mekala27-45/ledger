"""The stated parameters every document quotes, put into the manifest from config.

Policy numbers (the default definition, the chargeback window, the scorecard's
base points, the cost of a false decline) are assumptions, not results, so their
provenance is the config file and they are labelled static.
"""

from __future__ import annotations

from ledger_core.config import LedgerConfig
from ledger_core.manifest import Manifest


def policy_manifest(cfg: LedgerConfig) -> Manifest:
    m = Manifest(as_of=cfg.calendar.as_of.isoformat(), seed=cfg.seed)

    def put(key: str, value: float | int | str, fmt: str) -> None:
        m.put(f"policy.{key}", value, fmt, backend="static", population="config/ledger.yaml", source="config")

    put("bank_name", cfg.bank.name, "text")
    put("home_state", cfg.bank.home_state, "text")
    put("window_start", cfg.calendar.start.isoformat(), "text")
    put("as_of", cfg.calendar.as_of.isoformat(), "text")
    put("months", cfg.calendar.months, "int")
    put("seed", cfg.seed, "text")
    put("customers", cfg.generator.customers, "int")
    put("branches", cfg.generator.branches, "int")
    put("recession_first", cfg.generator.recession_months[0], "text")
    put("recession_last", cfg.generator.recession_months[-1], "text")
    put("default_window_months", cfg.censoring.default_window_months, "int")
    put("default_dpd", cfg.censoring.default_dpd, "int")
    put("cure_window_days", cfg.censoring.cure_window_days, "int")
    put("chargeback_window_days", cfg.censoring.chargeback_window_days, "int")
    put("cost_false_decline", cfg.fraud_desk.cost_false_decline, "usd2")
    put("cost_missed_fraud_handling", cfg.fraud_desk.cost_missed_fraud_handling, "usd2")
    put("queue_precision_floor", cfg.fraud_desk.queue_precision_floor, "pct0")
    put("replay_seconds_per_hour", cfg.fraud_desk.replay_speed_seconds_per_hour, "float1")
    put("base_score", cfg.scorecard.base_score, "int")
    put("base_odds", cfg.scorecard.base_odds, "int")
    put("pdo", cfg.scorecard.points_to_double_odds, "int")
    put("iv_floor", cfg.scorecard.iv_floor, "float2")
    put("correlation_ceiling", cfg.scorecard.correlation_ceiling, "float1")
    put("min_bin_share", cfg.scorecard.min_bin_share, "pct0")
    put("max_fine_bins", cfg.scorecard.max_fine_bins, "int")
    put("approval_cutoff", cfg.scorecard.approval_cutoff_score, "int")
    put("reason_codes", cfg.scorecard.reason_codes_returned, "int")
    put("reporting_threshold", cfg.aml.reporting_threshold, "usd0")
    put("structuring_floor", cfg.aml.structuring_floor, "usd0")
    put("structuring_window_days", cfg.aml.structuring_window_days, "int")
    put("rapid_movement_hours", cfg.aml.rapid_movement_hours, "int")
    put("mule_fan_in", cfg.aml.mule_fan_in_min_counterparties, "int")
    put("mule_window_days", cfg.aml.mule_window_days, "int")
    put("cycle_max_length", cfg.aml.cycle_max_length, "int")
    put("cycle_window_days", cfg.aml.cycle_window_days, "int")
    put("psi_warning", cfg.model_risk.psi_warning, "float2")
    put("psi_breach", cfg.model_risk.psi_breach, "float2")
    put("treasury_horizon_months", cfg.treasury.horizon_months, "int")
    put("ledger_break_account", cfg.generator.ledger_break.gl_account, "text")
    put("ledger_break_month", cfg.generator.ledger_break.month, "text")
    put("ledger_break_amount", cfg.generator.ledger_break.amount, "usd2")
    for product, weight in cfg.capital.risk_weights.items():
        put(f"risk_weight_{product}", weight, "pct0")
    for product, rate in cfg.liquidity.outflow_rates.items():
        put(f"outflow_rate_{product}", rate, "pct0")
    return m
