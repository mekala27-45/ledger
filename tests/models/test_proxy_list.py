"""No credit or fraud model uses a protected attribute or a listed proxy.

The feature lists are read from every model's published manifest, so a model
that is added later is checked without anyone remembering to add it here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ledger_scorecard.policy_files import load_proxies, model_feature_lists, proxy_hits

ROOT = Path(__file__).resolve().parents[2]
PROXIES = load_proxies(ROOT / "rules")


def test_every_published_model_is_clean() -> None:
    features = model_feature_lists(ROOT / "results" / "models")
    assert {"pd_scorecard", "pd_challenger", "fraud_card"} <= set(features)
    hits = proxy_hits(features, PROXIES)
    assert all(not found for found in hits.values()), hits


def test_a_model_using_a_proxy_is_caught(tmp_path: Path) -> None:
    folder = tmp_path / "bad_model"
    folder.mkdir()
    manifest = {
        "values": {"models.bad_model.features": {"value": "income, zip5, Applicant_Age", "fmt": "text"}}
    }
    (folder / "manifest.json").write_text(json.dumps(manifest))
    hits = proxy_hits(model_feature_lists(tmp_path), PROXIES)
    assert hits == {"bad_model": ["applicant_age", "zip5"]}


def test_refuses_to_pass_on_no_models(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no model feature lists"):
        proxy_hits(model_feature_lists(tmp_path), PROXIES)


def test_the_list_covers_the_protected_bases() -> None:
    for name in (
        "derived_race",
        "derived_ethnicity",
        "derived_sex",
        "applicant_age",
        "marital_status",
        "county_fips",
        "census_tract",
        "first_name",
    ):
        assert name in PROXIES
