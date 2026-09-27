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
