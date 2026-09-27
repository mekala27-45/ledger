from __future__ import annotations

from pathlib import Path

import pytest
from ledger_bankgen.generate import generate
from ledger_bankgen.params import GeneratorParams


@pytest.fixture(scope="session")
def small_bank(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, GeneratorParams]:
    root = tmp_path_factory.mktemp("bank")
    params = GeneratorParams().scaled(2500)
    generate(params, root / "raw", root / "truth", verbose=False)
    return root / "raw", root / "truth", params


@pytest.fixture(scope="session")
def clean_bank(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, GeneratorParams]:
    root = tmp_path_factory.mktemp("clean")
    params = (
        GeneratorParams()
        .scaled(1500)
        .model_copy(update={"inject_defects": False, "inject_ledger_break": False})
    )
    generate(params, root / "raw", root / "truth", verbose=False)
    return root / "raw", root / "truth", params
