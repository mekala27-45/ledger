"""From a trained model to its inventory entry, its manifest entries and its validation report data.

A validation report is rendered by the claim gate from ``models.<id>.*`` manifest
entries and the model's own template. This module writes those entries, reads the
effective challenge record from DECISIONS.md, and keeps the inventory.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl
from ledger_core.manifest import Manifest

from ledger_models.contract import CONTRACT_LINES, ModelCard
from ledger_models.evaluate import Discrimination
from ledger_models.gates import GateResult, conclusion

CHALLENGE = re.compile(r"^## (\d{4}-\d{2}-\d{2}): Challenge \(([^)]+)\): (.+)$")
FIELD = re.compile(r"^\*\*(Raised|Response|Changed):\*\*\s*(.*)$")


@dataclass(frozen=True)
class Challenge:
    date: str
    models: tuple[str, ...]
    question: str
    raised: str
    response: str
    changed: str


def read_challenges(decisions: Path) -> list[Challenge]:
    """Effective challenge entries: '## date: Challenge (model, model): question' with three fields."""
    out: list[Challenge] = []
    lines = decisions.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        m = CHALLENGE.match(lines[i])
        if not m:
            i += 1
            continue
        fields: dict[str, list[str]] = {"Raised": [], "Response": [], "Changed": []}
        current: str | None = None
        i += 1
        while i < len(lines) and not lines[i].startswith("## "):
            f = FIELD.match(lines[i])
            if f:
                current = f.group(1)
                fields[current].append(f.group(2))
            elif current and lines[i].strip():
                fields[current].append(lines[i].strip())
            i += 1
        text = {k: " ".join(v).strip() for k, v in fields.items()}
        if not all(text.values()):
            raise ValueError(f"challenge '{m.group(3)}' is missing Raised, Response or Changed")
        models = tuple(x.strip() for x in m.group(2).split(","))
        out.append(
            Challenge(
                m.group(1), models, m.group(3).strip(), text["Raised"], text["Response"], text["Changed"]
            )
        )
    return out


@dataclass
class ModelResult:
    card: ModelCard
    samples: dict[str, Discrimination]  # development, validation, test
    baselines: dict[str, Discrimination]  # name -> test sample discrimination
    gates: list[GateResult]
    reliability: pl.DataFrame
    subgroups: pl.DataFrame | None = None
    subgroup_note: str = ""
    extra_values: dict[str, tuple[float | int | str | None, str]] = field(default_factory=dict)
    extra_tables: dict[str, pl.DataFrame] = field(default_factory=dict)
    extra_formats: dict[str, list[str]] = field(default_factory=dict)
    monitoring: list[tuple[str, str, str]] = field(default_factory=list)  # (measure, trigger, action)
    last_validated: str = ""

    def verdict(self) -> tuple[str, list[str]]:
        return conclusion(self.gates)


def _prov(result: ModelResult, source: str) -> dict[str, Any]:
    backend = result.card.backend
    return {"backend": backend, "population": result.card.population, "source": source}


def put_result(m: Manifest, result: ModelResult, challenges: list[Challenge]) -> None:
    mid = result.card.model_id
    k = f"models.{mid}"
    prov = _prov(result, f"packages/models ({mid})")
    for sample, d in result.samples.items():
        for measure, fmt in (
            ("auroc", "float3"),
            ("gini", "float3"),
            ("ks", "float3"),
            ("brier", "float4"),
            ("ece", "float4"),
            ("event_rate", "pct2"),
            ("average_precision", "float3"),
        ):
            m.put(f"{k}.{sample}.{measure}", getattr(d, measure), fmt, **prov)
        m.put(f"{k}.{sample}.n", d.n, "int", **prov)
        m.put(f"{k}.{sample}.events", d.events, "int", **prov)
    rows: list[list[float | int | str | None]] = [
        [
            "This model",
            result.samples["test"].auroc,
            result.samples["test"].gini,
            result.samples["test"].brier,
            result.samples["test"].ece,
        ]
    ]
    for name, d in result.baselines.items():
        rows.append([name, d.auroc, d.gini, d.brier, d.ece])
    m.put_table(
        f"{k}.benchmark",
        ["Model", "AUROC", "Gini", "Brier", "ECE"],
        ["text", "float3", "float3", "float4", "float4"],
        rows,
        **prov,
    )
    m.put_table(
        f"{k}.gates",
        ["Gate", "Threshold", "Measured", "Result"],
        ["text", "text", "float4", "text"],
        [[r.gate.statement, _threshold(r), r.value, "pass" if r.passed else "FAIL"] for r in result.gates],
        **prov,
    )
    verdict, conditions = result.verdict()
    m.put(f"{k}.conclusion", verdict, "text", **prov)
    m.put(f"{k}.conditions_count", len(conditions), "int", **prov)
    m.put_table(f"{k}.conditions", ["Condition"], ["text"], [[c] for c in conditions] or [["None"]], **prov)
    m.put_table(
        f"{k}.reliability",
        ["Bin", "Accounts", "Predicted", "Observed"],
        ["int", "int", "pct2", "pct2"],
        result.reliability.select("bin", "n", "predicted", "observed").rows(),
        **prov,
    )
    if result.subgroups is not None and result.subgroups.height:
        order = (
            "group",
            "n",
            "event_rate",
            "mean_score",
            "calibration_gap",
            "auroc",
            "flag_rate",
            "fpr",
            "recall",
            "approval_rate",
            "adverse_impact_ratio",
        )
        cols = [c for c in order if c in result.subgroups.columns]
        fmts = {
            "group": "text",
            "n": "int",
            "event_rate": "pct2",
            "mean_score": "pct2",
            "calibration_gap": "spct1",
            "auroc": "float3",
            "flag_rate": "pct2",
            "fpr": "pct2",
            "recall": "pct1",
            "approval_rate": "pct1",
            "adverse_impact_ratio": "float2",
        }
        m.put_table(
            f"{k}.subgroups",
            [c.replace("_", " ").capitalize() for c in cols],
            [fmts[c] for c in cols],
            result.subgroups.select(cols).rows(),
            **prov,
        )
    card = result.card
    m.put_table(
        f"{k}.contract",
        ["Line", "What this model does"],
        ["text", "text"],
        [[line, card.lines[line]] for line in CONTRACT_LINES],
        **prov,
    )
    for key, value in (
        ("title", card.title),
        ("purpose", card.purpose),
        ("tier", str(card.tier)),
        ("tier_reason", card.tier_reason),
        ("role", card.role),
        ("status", card.status),
        ("prediction_time", card.prediction_time),
        ("outcome", card.outcome),
        ("method", card.method),
        ("owner", card.owner),
        ("features", ", ".join(card.features)),
        ("feature_count", str(len(card.features))),
        ("last_validated", result.last_validated),
    ):
        m.put(f"{k}.{key}", value, "text", **prov)
    mine = [c for c in challenges if mid in c.models]
    if len(mine) < 2:
        raise ValueError(
            f"{mid} has {len(mine)} effective challenges on record; the policy asks for at least two"
        )
    m.put_table(
        f"{k}.challenges",
        ["Date", "Challenge", "Response", "What changed"],
        ["text"] * 4,
        [[c.date, c.raised, c.response, c.changed] for c in mine],
        **prov,
    )
    m.put_table(
        f"{k}.monitoring",
        ["Measure", "Trigger", "Action"],
        ["text"] * 3,
        [list(r) for r in result.monitoring] or [["None stated", "", ""]],
        **prov,
    )
    for extra_key, (extra_value, value_fmt) in result.extra_values.items():
        m.put(f"{k}.{extra_key}", extra_value, value_fmt, **prov)
    for table_key, frame in result.extra_tables.items():
        table_fmts = result.extra_formats.get(table_key) or ["text"] * frame.width
        m.put_table(f"{k}.{table_key}", frame.columns, table_fmts, frame.rows(), **prov)


def _threshold(r: GateResult) -> str:
    g = r.gate
    if g.comparison == "at_least":
        return f"at least {g.threshold:g}"
    if g.comparison == "at_most":
        return f"at most {g.threshold:g}"
    return f"{g.threshold:g} to {g.upper:g}"


def inventory_row(result: ModelResult) -> dict[str, Any]:
    card = result.card
    verdict, conditions = result.verdict()
    return {
        "model_id": card.model_id,
        "title": card.title,
        "function": card.function,
        "owner": card.owner,
        "purpose": card.purpose,
        "tier": card.tier,
        "status": card.status,
        "role": card.role,
        "last_validated": result.last_validated,
        "conclusion": verdict,
        "conditions": conditions,
        "auroc_test": result.samples["test"].auroc,
        "monitoring": [list(r) for r in result.monitoring],
    }


def write_inventory(models_dir: Path, rows: list[dict[str, Any]]) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)
    path = models_dir / "registry.json"
    existing: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {}
    for row in rows:
        existing[row["model_id"]] = row
    path.write_text(json.dumps(dict(sorted(existing.items())), indent=1, sort_keys=True) + "\n")
