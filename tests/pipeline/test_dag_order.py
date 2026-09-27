"""The Airflow DAG runs the pipeline in the Makefile's order."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def makefile_pipeline() -> list[str]:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    line = re.search(r"^pipeline:(.*)$", text, flags=re.MULTILINE)
    assert line, "the Makefile has no pipeline target"
    return line.group(1).split()


def dag_stages() -> list[str]:
    spec = importlib.util.spec_from_file_location("ledger_dag", ROOT / "dags" / "ledger.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.STAGES)


def test_the_dag_and_the_makefile_agree() -> None:
    assert dag_stages() == makefile_pipeline()


def test_every_stage_is_a_make_target() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^([a-z-]+):", text, flags=re.MULTILINE))
    assert set(dag_stages()) <= targets


def test_models_run_before_the_functions_that_read_them() -> None:
    stages = dag_stages()
    assert (
        stages.index("warehouse")
        < stages.index("models")
        < stages.index("functions")
        < stages.index("manifest")
    )
    assert stages.index("render") < stages.index("site-data")


def recipe(target: str) -> list[str]:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    block = re.search(rf"^{re.escape(target)}:.*\n((?:\t.*\n?)*)", text, flags=re.MULTILINE)
    assert block, f"the Makefile has no {target} target"
    return [line.strip() for line in block.group(1).splitlines() if line.strip()]


def test_the_warehouse_is_built_through_the_cli() -> None:
    # dbt called bare from the warehouse folder bakes a relative path to the staged tables
    # into every staging view, and every stage after it that opens the database from the
    # repository root then fails. The CLI hands dbt absolute paths.
    assert recipe("warehouse") == ["$(LEDGER) warehouse"]
