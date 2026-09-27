"""Every parameter the generator uses, stated in one place.

These are the known truth. The pipeline is expected to recover the ones marked
``recover`` within a stated tolerance before any number it produces is trusted
(tests/bankgen/test_known_parameter_recovery.py and results/f02 known_parameters).
"""

from __future__ import annotations

from datetime import date

from ledger_core.model import StrictModel


class MacroPath(StrictModel):
    """The generated bank's own macro history. Not the real economy, and labelled so."""

    unemployment_start: float = 3.9
    unemployment_peak: float = 6.4
    unemployment_end: float = 5.0
    policy_rate_start: float = 5.33
    policy_rate_pre_shock: float = 4.50
    policy_rate_shock_bps: int = -150
    policy_rate_end: float = 2.75
    hpi_growth_normal: float = 0.045
    hpi_growth_recession: float = -0.06


class DefaultProcess(StrictModel):
    """Monthly hazard of a current installment loan rolling to 30 days past due.

    logit(h) = intercept + beta_risk * z + beta_macro * (unemployment - 4.0)
               + vintage_effect[vintage] + seasoning(months on book)
    """

    intercept: float = -4.55
    beta_risk: float = 0.95
    beta_macro: float = 0.30  # recover: per percentage point of unemployment
    loose_vintages: tuple[str, ...] = ("2024Q4", "2025Q1")
    vintage_effect: float = 0.45  # recover: logit shift for the loose underwriting vintages
    seasoning_peak_month: int = 10
    seasoning_amplitude: float = 0.55
    cure_from_30: float = 0.42
    cure_from_60: float = 0.22
    cure_from_90: float = 0.10
    roll_30_to_60: float = 0.55
    roll_60_to_90: float = 0.70
    roll_90_to_120: float = 0.78
    risk_on_roll: float = 0.25
    chargeoff_dpd_installment: int = 120
    chargeoff_dpd_card: int = 180
    prepay_monthly: float = 0.014
    recovery_share_24m: float = 0.22  # recover: cumulative recovery after charge off, installment


class DepositBetas(StrictModel):
    """Share of a policy rate change passed through to each product's rate. recover: all three."""

    checking: float = 0.02
    savings: float = 0.38
    time: float = 0.72
    checking_floor: float = 0.05
    savings_floor: float = 0.25
    savings_start: float = 2.05
    time_spread: float = -0.55


class Attrition(StrictModel):
    """Monthly hazard of a customer closing their primary checking account."""

    intercept: float = -5.10
    new_customer: float = 0.85
    balance_decline: float = 0.70
    fee_last_month: float = 0.45
    digital_active: float = -0.35
    rate_gap_per_point: float = 0.25
    complaint: float = 0.95


class Typologies(StrictModel):
    """Financial crime patterns injected with known membership, at stated counts."""

    structuring_customers: int = 90
    rapid_movement_customers: int = 60
    mule_customers: int = 70
    round_trip_rings: int = 15
    cash_intensive_lookalikes: int = 320
    p2p_heavy_lookalikes: int = 400
    large_wire_lookalikes: int = 150


class Defects(StrictModel):
    """Data defects injected at stated rates so the quality checks have something real to find."""

    duplicated_posting_rate: float = 0.0004
    missing_counterparty_rate: float = 0.0002
    non_rolling_balance_rate: float = 0.0001
    ledger_break_account: str = "2010"
    ledger_break_month: str = "2026-03"
    ledger_break_amount: float = 4217.36


class GeneratorParams(StrictModel):
    seed: int = 20260831
    start: date = date(2023, 9, 1)
    months: int = 36
    customers: int = 50_000
    branches: int = 18
    recession_months: tuple[str, ...] = ("2025-03", "2025-04", "2025-05")
    applications_per_month: int = 1000
    card_share: float = 0.30
    mortgage_share: float = 0.08
    savings_share: float = 0.55
    cd_share: float = 0.12
    checking_share: float = 0.92
    opex_per_customer_month: float = 52.0
    macro: MacroPath = MacroPath()
    default: DefaultProcess = DefaultProcess()
    betas: DepositBetas = DepositBetas()
    attrition: Attrition = Attrition()
    typologies: Typologies = Typologies()
    defects: Defects = Defects()
    inject_ledger_break: bool = True
    inject_defects: bool = True

    def scaled(self, customers: int, applications_per_month: int | None = None) -> GeneratorParams:
        """A smaller bank with the same parameters, for tests and CI."""
        factor = customers / self.customers
        typ = self.typologies.model_copy(
            update={
                k: max(2 if k == "round_trip_rings" else 3, round(v * factor))
                for k, v in self.typologies.model_dump().items()
            }
        )
        return self.model_copy(
            update={
                "customers": customers,
                "applications_per_month": applications_per_month
                or max(40, round(self.applications_per_month * factor)),
                "typologies": typ,
            }
        )
