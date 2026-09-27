from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("LEDGER_ROOT", str(ROOT))

from ledger_bankgen.generate import generate  # noqa: E402
from ledger_bankgen.params import GeneratorParams  # noqa: E402


@pytest.fixture(scope="session")
def small_bank(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, GeneratorParams]:
    """A 2,500 customer bank with every defect and the ledger break injected."""
    root = tmp_path_factory.mktemp("bank")
    params = GeneratorParams().scaled(2500)
    generate(params, root / "raw", root / "truth", verbose=False)
    return root / "raw", root / "truth", params


@pytest.fixture(scope="session")
def clean_bank(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, GeneratorParams]:
    """A 1,500 customer bank with no defects and no ledger break."""
    root = tmp_path_factory.mktemp("clean")
    params = (
        GeneratorParams()
        .scaled(1500)
        .model_copy(update={"inject_defects": False, "inject_ledger_break": False})
    )
    generate(params, root / "raw", root / "truth", verbose=False)
    return root / "raw", root / "truth", params
