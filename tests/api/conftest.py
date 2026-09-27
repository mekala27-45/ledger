"""API fixtures: a real Postgres, a small scored stream, and a client with a token.

Every test that checks persistence reads back through a connection opened for the
purpose, never through the application's session.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import polars as pl
import psycopg
import pytest
from fastapi.testclient import TestClient
from ledger_api.app import create_app
from ledger_api.db import SQLModel, make_engine
from ledger_api.settings import Settings
from ledger_desk.fixtures import sample_stream

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "test-token-not-a-secret"
DEFAULT_URL = "postgresql+psycopg://postgres@127.0.0.1:5433/ledger_test"


def _url() -> str:
    return os.environ.get("LEDGER_TEST_DATABASE_URL", DEFAULT_URL)


def plain_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _url()
    try:
        with psycopg.connect(plain_url(url), connect_timeout=3):
            pass
    except psycopg.OperationalError:
        pytest.skip(f"no Postgres reachable at {url}")
    return url


@pytest.fixture()
def clean_db(database_url: str) -> str:
    engine = make_engine(database_url)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    engine.dispose()
    return database_url


def fixture_stream(n: int = 40) -> pl.DataFrame:
    return sample_stream(n)


@pytest.fixture()
def settings(clean_db: str, tmp_path: Path) -> Settings:
    stream = tmp_path / "replay_stream.parquet"
    fixture_stream().write_parquet(stream)
    return Settings(
        database_url=clean_db,
        api_token=TOKEN,
        results=ROOT / "results",
        rules=ROOT / "rules",
        replay_seconds_per_hour=0.0,
        replay_file=stream,
        environment="test",
    )


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, start_desk=False)
    with TestClient(app) as test_client:
        yield test_client


def auth() -> dict[str, str]:
    return {"authorization": f"Bearer {TOKEN}", "x-ledger-actor": "test_analyst"}


def rows(url: str, query: str) -> list[tuple[object, ...]]:
    """Read through a brand new connection, as a separate observer would."""
    with psycopg.connect(plain_url(url)) as conn, conn.cursor() as cur:
        cur.execute(query)
        return list(cur.fetchall())
