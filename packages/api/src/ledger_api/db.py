"""Tables for everything the API persists across a request boundary.

Alerts, cases, case events, score decisions and the audit log. Every one of them
is observed from an independently opened connection in the tests, because a test
that shares the application's session cannot see a missing commit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, text
from sqlmodel import Field, Session, SQLModel, create_engine, select


def now() -> datetime:
    return datetime.now(UTC)


class Alert(SQLModel, table=True):
    __tablename__ = "alerts"
    id: int | None = Field(default=None, primary_key=True)
    txn_id: int = Field(index=True, unique=True)
    transaction_time: datetime
    card_key: str
    category: str
    amount: float
    score: float
    decision: str  # review or decline
    queue: bool
    rules: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    model_reasons: str = ""
    status: str = "open"  # open, in_case, closed
    created_at: datetime = Field(default_factory=now)


class Case(SQLModel, table=True):
    __tablename__ = "cases"
    id: int | None = Field(default=None, primary_key=True)
    alert_id: int = Field(foreign_key="alerts.id", index=True)
    status: str = "open"  # open, escalated, closed
    assignee: str | None = None
    disposition: str | None = None  # closed_no_action, escalated_for_sar_review, kept_open
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class CaseEvent(SQLModel, table=True):
    __tablename__ = "case_events"
    id: int | None = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="cases.id", index=True)
    action: str
    actor: str
    note: str = ""
    at: datetime = Field(default_factory=now)


class ScoreDecision(SQLModel, table=True):
    __tablename__ = "score_decisions"
    id: int | None = Field(default=None, primary_key=True)
    model_id: str = Field(index=True)
    request_digest: str
    score: float
    probability: float
    decision: str
    reasons: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    at: datetime = Field(default_factory=now)


class AuditEntry(SQLModel, table=True):
    __tablename__ = "audit_log"
    id: int | None = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=now, index=True)
    actor: str
    action: str
    resource: str
    resource_id: str = ""
    detail: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


def schema_options(schema: str = "") -> dict[str, Any]:
    """With a schema, every table name the engine emits is qualified with it, so the tables live
    there whatever the connection's search path says. A hosted database's connection proxy can drop
    a search path set through the startup options, which is why the path is not relied on."""
    if not schema:
        return {}
    return {"schema_translate_map": {None: schema}}


def make_engine(url: str, schema: str = "") -> Any:
    engine = create_engine(url, pool_pre_ping=True)
    return engine.execution_options(**schema_options(schema)) if schema else engine


def ensure_schema(url: str, schema: str) -> None:
    """Create the schema if it is missing; a no op without one."""
    if not schema:
        return
    engine = create_engine(url, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text(f'create schema if not exists "{schema}"'))
    engine.dispose()


def create_all(engine: Any) -> None:
    SQLModel.metadata.create_all(engine)


def reset(engine: Any) -> None:
    """Clear every table the demo writes to. Used by reset and rederive before publish."""
    with Session(engine) as session:
        for table in (CaseEvent, Case, ScoreDecision, AuditEntry, Alert):
            for row in session.exec(select(table)).all():
                session.delete(row)
        session.commit()
