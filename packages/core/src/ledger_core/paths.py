"""Where everything lives. Resolved once from the repository root."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _find_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        marker = candidate / "config" / "ledger.yaml"
        if marker.is_file() and (candidate / "pyproject.toml").is_file():
            return candidate
    raise FileNotFoundError(f"Could not find the ledger repository root above {start}")


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def config(self) -> Path:
        return self.root / "config" / "ledger.yaml"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def generated(self) -> Path:
        return self.raw / "generated"

    @property
    def sparkov(self) -> Path:
        return self.raw / "sparkov"

    @property
    def external(self) -> Path:
        return self.data / "external"

    @property
    def staged(self) -> Path:
        return self.data / "staged"

    @property
    def quarantine(self) -> Path:
        return self.data / "quarantine"

    @property
    def reference(self) -> Path:
        return self.data / "reference"

    @property
    def warehouse_dir(self) -> Path:
        return self.root / "warehouse"

    @property
    def warehouse_db(self) -> Path:
        override = os.environ.get("LEDGER_WAREHOUSE")
        return Path(override) if override else self.warehouse_dir / "ledger.duckdb"

    @property
    def results(self) -> Path:
        return self.root / "results"

    @property
    def manifest(self) -> Path:
        return self.results / "manifest.json"

    @property
    def models_dir(self) -> Path:
        return self.results / "models"

    @property
    def report(self) -> Path:
        return self.root / "report"

    @property
    def docs(self) -> Path:
        return self.root / "docs"

    @property
    def rules(self) -> Path:
        return self.root / "rules"

    @property
    def metrics(self) -> Path:
        return self.root / "metrics"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def web_data(self) -> Path:
        return self.root / "web" / "public" / "data"


@lru_cache(maxsize=1)
def paths() -> Paths:
    override = os.environ.get("LEDGER_ROOT")
    start = Path(override) if override else Path(__file__).resolve()
    return Paths(_find_root(start))
