"""Readers for the committed proxy list and reason code table."""

from __future__ import annotations

from pathlib import Path

import yaml


def load_proxies(rules_dir: Path) -> set[str]:
    data = yaml.safe_load((rules_dir / "proxies.yaml").read_text(encoding="utf-8"))
    return {str(x).lower() for x in data["protected"]} | {str(x).lower() for x in data["proxies"]}


def load_reason_codes(rules_dir: Path, population: str) -> dict[str, str]:
    data = yaml.safe_load((rules_dir / "reason_codes.yaml").read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data[population].items()}


def model_feature_lists(models_dir: Path) -> dict[str, list[str]]:
    """Every documented model's feature list, read from its partial manifest."""
    import json

    features: dict[str, list[str]] = {}
    for path in sorted(models_dir.glob("*/manifest.json")):
        values = json.loads(path.read_text(encoding="utf-8")).get("values", {})
        for key, entry in values.items():
            if key.endswith(".features") and isinstance(entry.get("value"), str):
                features[key.split(".")[1]] = [f.strip() for f in entry["value"].split(",") if f.strip()]
    return features


def proxy_hits(features: dict[str, list[str]], proxies: set[str]) -> dict[str, list[str]]:
    """For each model, the protected attributes or listed proxies among its features."""
    if not features:
        raise ValueError("no model feature lists to check")
    return {model: sorted({f.lower() for f in fs} & proxies) for model, fs in features.items()}
