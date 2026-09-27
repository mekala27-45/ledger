"""The desk's rules: small, stated, and in plain words."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl
import yaml


@dataclass(frozen=True)
class DeskRules:
    new_category_amount: float
    burst_count: int
    burst_minutes: int
    distant_km: float
    distant_minutes: int
    statements: dict[str, str]


def load_rules(rules_dir: Path) -> DeskRules:
    data = yaml.safe_load((rules_dir / "fraud_rules.yaml").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in data["rules"]}
    nc, burst, far = by_id["new_category_large"], by_id["burst"], by_id["distant_merchant"]
    statements = {
        "new_category_large": nc["statement"].replace("{amount}", f"{nc['amount']:,}"),
        "burst": burst["statement"].replace("{minutes}", str(burst["minutes"])),
        "distant_merchant": far["statement"].replace("{km}", str(far["km"])),
    }
    return DeskRules(
        float(nc["amount"]),
        int(burst["count"]),
        int(burst["minutes"]),
        float(far["km"]),
        int(far["minutes"]),
        statements,
    )


def rule_columns(features: pl.DataFrame, rules: DeskRules) -> pl.DataFrame:
    """One boolean column per rule. Needs count_10m, new_category, km_from_last_merchant and seconds_since_last."""
    if features.height == 0:
        raise ValueError("refusing to evaluate rules on no transactions")
    if rules.burst_minutes != 10:
        raise ValueError(
            "the burst rule reads the ten minute window; change the feature window to change the rule"
        )
    return features.select(
        "txn_id",
        rule_new_category_large=(pl.col("new_category") == 1.0)
        & (pl.col("amount") > rules.new_category_amount),
        rule_burst=(pl.col("count_10m") + 1) >= rules.burst_count,
        rule_distant_merchant=(pl.col("km_from_last_merchant") > rules.distant_km)
        & (pl.col("seconds_since_last") <= rules.distant_minutes * 60),
    ).with_columns(pl.col("^rule_.*$").fill_null(False))


def fired_list(row: dict[str, object], rules: DeskRules) -> list[str]:
    return [rules.statements[k] for k in rules.statements if row.get(f"rule_{k}")]
