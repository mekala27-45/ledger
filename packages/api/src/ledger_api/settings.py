"""Runtime settings, read from the environment once."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_token: str
    results: Path
    rules: Path
    replay_seconds_per_hour: float
    replay_file: Path
    environment: str
    replay_loop: bool = True
    # Origins allowed to call the API from a browser, such as the static site's host.
    cors_origins: tuple[str, ...] = ()

    @property
    def token_required(self) -> bool:
        return bool(self.api_token)


def load_settings() -> Settings:
    root = Path(os.environ.get("LEDGER_ROOT", Path(__file__).resolve().parents[4]))
    results = root / "results"
    return Settings(
        database_url=os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5433/ledger"),
        api_token=os.environ.get("LEDGER_API_TOKEN", ""),
        results=results,
        rules=root / "rules",
        replay_seconds_per_hour=float(os.environ.get("LEDGER_REPLAY_SECONDS_PER_HOUR", "1.0")),
        replay_file=Path(
            os.environ.get("LEDGER_REPLAY_FILE", results / "models" / "fraud_card" / "replay_stream.parquet")
        ),
        environment=os.environ.get("LEDGER_ENV", "development"),
        replay_loop=os.environ.get("LEDGER_REPLAY_LOOP", "1") != "0",
        cors_origins=tuple(
            o.strip() for o in os.environ.get("LEDGER_CORS_ORIGINS", "").split(",") if o.strip()
        ),
    )
