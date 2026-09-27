"""The model integration contract, banking edition: thirteen lines every model must fill.

Day 8's eleven lines (trained, timed, calibrated, useful, fair, gated, served,
integrated, monitored, documented, bounded) plus the two banking lines:
``validated`` (an SR 11-7 style validation report exists before the model is used
anywhere) and ``explainable`` (a decision it informs carries reasons a regulator
would accept). A model whose card leaves a line empty cannot be registered.
"""

from __future__ import annotations

from typing import Literal

from ledger_core.model import StrictModel
from pydantic import Field, model_validator

Tier = Literal[1, 2, 3]
Status = Literal["development", "validated", "in use", "retired"]
Role = Literal["champion", "challenger", "sole"]
Conclusion = Literal["approved", "approved with conditions", "not approved"]

CONTRACT_LINES = (
    "trained",
    "timed",
    "calibrated",
    "useful",
    "fair",
    "gated",
    "served",
    "integrated",
    "monitored",
    "documented",
    "bounded",
    "validated",
    "explainable",
)

REPORT_SECTIONS = (
    "purpose",
    "soundness",
    "data",
    "development",
    "outcomes",
    "benchmarking",
    "limitations",
    "monitoring",
    "challenge",
    "conclusion",
)


class ContractError(ValueError):
    pass


class ModelCard(StrictModel):
    model_id: str
    function: str
    title: str
    purpose: str
    owner: str = "Head of analytics"
    tier: Tier
    tier_reason: str
    role: Role
    status: Status
    prediction_time: str
    outcome: str
    population: str
    backend: str
    method: str
    features: list[str]
    lines: dict[str, str] = Field(description="each contract line in one or two plain sentences")

    @model_validator(mode="after")
    def _every_line_filled(self) -> ModelCard:
        missing = [line for line in CONTRACT_LINES if not self.lines.get(line, "").strip()]
        extra = sorted(set(self.lines) - set(CONTRACT_LINES))
        if missing:
            raise ContractError(f"{self.model_id}: contract lines left empty: {missing}")
        if extra:
            raise ContractError(f"{self.model_id}: lines that are not in the contract: {extra}")
        return self


def tier_for(*, decides_automatically: bool, informs_person: bool, complex_method: bool) -> tuple[Tier, str]:
    """The stated tiering rule: materiality first, complexity as a tie breaker upward."""
    if decides_automatically:
        return 1, "Material: informs a credit, fraud or regulatory decision directly"
    if informs_person and complex_method:
        return 1, "Informs a decision a person makes, with a method whose behaviour is hard to inspect"
    if informs_person:
        return 2, "Informs a decision a person makes; moderate materiality"
    return 3, "Analytical or monitoring use; low materiality"
