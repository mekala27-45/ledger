"""Small warehouses built by the real dbt project over small generated banks.

Building the warehouse is the step under test, so these fixtures run it rather
than faking its output: contracts, then dbt build with every dbt test, over a
2,500 customer bank with its defects and ledger break, and a 1,500 customer bank
with neither. Real datasets and the card stream are excluded by tag.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from ledger_bankgen.generate import generate
from ledger_bankgen.params import GeneratorParams
from ledger_contracts.run import run_contracts
from ledger_core.paths import Paths, paths
from ledger_functions.warehouse import build

pytestmark = pytest.mark.warehouse


def _bank(root: Path, params: GeneratorParams) -> Path:
    generate(params, root / "data" / "raw" / "generated", root / "data" / "raw" / "truth", verbose=False)
    run_contracts(Paths(root), include_real=False, include_cards=False)
    database = root / "warehouse.duckdb"
    build(paths(), staged=root / "data" / "staged", database=database, exclude=["tag:real", "tag:stream"])
    return root


@pytest.fixture(scope="session")
def broken_warehouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("dbt") is None and not (Path(__import__("sys").executable).parent / "dbt").exists():
        pytest.skip("dbt is not installed")
    return _bank(tmp_path_factory.mktemp("broken"), GeneratorParams().scaled(2500))


@pytest.fixture(scope="session")
def clean_warehouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("dbt") is None and not (Path(__import__("sys").executable).parent / "dbt").exists():
        pytest.skip("dbt is not installed")
    params = (
        GeneratorParams()
        .scaled(1500)
        .model_copy(update={"inject_defects": False, "inject_ledger_break": False})
    )
    return _bank(tmp_path_factory.mktemp("clean"), params)
