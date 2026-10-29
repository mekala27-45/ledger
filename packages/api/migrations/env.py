"""Alembic environment: the database URL comes from DATABASE_URL, the schema from the SQLModel tables.

With LEDGER_DB_SCHEMA set, the tables and alembic's own version table live in that schema, so the
other projects' tables in a shared database are never touched, and another project's version table
(also at a revision 0001) is never mistaken for this one's.
"""

from __future__ import annotations

import os

import ledger_api.db  # noqa: F401  (registers the tables on SQLModel.metadata)
from alembic import context
from ledger_api.settings import normalize_database_url
from sqlalchemy import engine_from_config, pool, text
from sqlmodel import SQLModel

config = context.config
config.set_main_option(
    "sqlalchemy.url",
    normalize_database_url(
        os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5433/ledger")
    ).replace("%", "%%"),
)
target_metadata = SQLModel.metadata
SCHEMA = os.environ.get("LEDGER_DB_SCHEMA", "").strip()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {}, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        if SCHEMA:
            connection.execute(text(f'create schema if not exists "{SCHEMA}"'))
            connection.commit()
        context.configure(
            connection=connection, target_metadata=target_metadata, version_table_schema=SCHEMA or None
        )
        with context.begin_transaction():
            if SCHEMA:
                # Inside the migration's own transaction, so a pooled connection cannot lose it.
                connection.execute(text(f'set local search_path to "{SCHEMA}", public'))
            context.run_migrations()


run_migrations_online()
