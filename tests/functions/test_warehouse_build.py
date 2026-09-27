"""Building a warehouse, and reading the record of the last full build.

A test build writes into its own folder and must leave the real warehouse's dbt record
alone, because the controls function publishes its model and test counts from that record.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ledger_core.paths import Paths
from ledger_functions.warehouse import WarehouseError, build_args, last_full_build

ROOT = Path(__file__).resolve().parents[2]


def test_the_real_warehouse_keeps_its_artifacts_in_the_project() -> None:
    p = Paths(ROOT)
    args = build_args(p)
    assert "--target-path" not in args and "--log-path" not in args
    assert build_args(p, database=p.warehouse_db) == args


def test_a_build_elsewhere_keeps_its_artifacts_beside_its_database(tmp_path: Path) -> None:
    p = Paths(ROOT)
    args = build_args(p, database=tmp_path / "warehouse.duckdb", exclude=["tag:real"])
    target = Path(args[args.index("--target-path") + 1])
    logs = Path(args[args.index("--log-path") + 1])
    assert target.is_relative_to(tmp_path.resolve()) and logs.is_relative_to(tmp_path.resolve())
    assert not target.is_relative_to(p.warehouse_dir)
    assert args[-2:] == ["--exclude", "tag:real"]


def _record(tmp_path: Path, args: dict[str, object], results: list[dict[str, str]]) -> Path:
    path = tmp_path / "run_results.json"
    path.write_text(json.dumps({"args": args, "results": results}), encoding="utf-8")
    return path


RESULTS = [
    {"unique_id": "model.ledger.stg_gl_postings", "status": "success"},
    {"unique_id": "model.ledger.mart_bank_month", "status": "success"},
    {"unique_id": "test.ledger.not_null_month", "status": "pass"},
    {"unique_id": "test.ledger.unique_month", "status": "fail"},
    {"unique_id": "exposure.ledger.page_glance", "status": "no-op"},
]


def test_a_full_build_is_counted(tmp_path: Path) -> None:
    record = last_full_build(_record(tmp_path, {"which": "build", "select": [], "exclude": []}, RESULTS))
    assert (record.models, record.tests, record.tests_passed) == (2, 2, 1)


@pytest.mark.parametrize(
    "args",
    [
        {"which": "build", "select": [], "exclude": ["tag:real", "tag:stream"]},  # the test fixtures' build
        {"which": "build", "select": ["marts"], "exclude": []},
        {"which": "run", "select": [], "exclude": []},
    ],
)
def test_a_partial_build_is_refused(tmp_path: Path, args: dict[str, object]) -> None:
    with pytest.raises(WarehouseError, match="partial"):
        last_full_build(_record(tmp_path, args, RESULTS))


def test_no_record_and_an_empty_record_are_refused(tmp_path: Path) -> None:
    with pytest.raises(WarehouseError, match="no dbt run record"):
        last_full_build(tmp_path / "missing.json")
    with pytest.raises(WarehouseError, match="no models"):
        last_full_build(_record(tmp_path, {"which": "build", "select": [], "exclude": []}, []))
