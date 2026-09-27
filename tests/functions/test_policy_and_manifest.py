"""Policy parameters reach documents only through the manifest, and partial manifests merge once."""

from __future__ import annotations

from pathlib import Path

import pytest
from ledger_core.config import load_config
from ledger_core.manifest import Manifest
from ledger_core.paths import Paths
from ledger_functions.policy import policy_manifest
from ledger_functions.registry import merge_manifest

ROOT = Path(__file__).resolve().parents[2]


def test_policy_manifest_carries_the_stated_parameters() -> None:
    cfg = load_config(ROOT / "config" / "ledger.yaml")
    m = policy_manifest(cfg)
    assert m.raw("policy.default_dpd") == cfg.censoring.default_dpd
    assert m.raw("policy.chargeback_window_days") == cfg.censoring.chargeback_window_days
    assert m.text("policy.cost_false_decline") == "$12.00"
    assert m.values["policy.base_score"].provenance.backend == "static"


def test_partial_manifests_merge_and_a_duplicate_key_is_refused(tmp_path: Path) -> None:
    cfg = load_config(ROOT / "config" / "ledger.yaml")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "ledger.yaml").write_text((ROOT / "config" / "ledger.yaml").read_text())
    p = Paths(tmp_path)
    part = Manifest(as_of="2026-08-31", seed=1)
    part.put("f99.x", 1.5, "float1", backend="generated", population="bank", source="test")
    (p.results / "f99").mkdir(parents=True)
    part.save(p.results / "f99" / "manifest.json")
    merged = merge_manifest(p, cfg)
    assert merged.raw("f99.x") == 1.5 and merged.raw("policy.months") == cfg.calendar.months
    clash = Manifest(as_of="2026-08-31", seed=1)
    clash.put("f99.x", 2.0, "float1", backend="generated", population="bank", source="test")
    (p.results / "f98").mkdir()
    clash.save(p.results / "f98" / "manifest.json")
    with pytest.raises(ValueError, match="written twice"):
        merge_manifest(p, cfg)
