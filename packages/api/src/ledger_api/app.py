"""The ledger API: scoring, the scorecard, the desk stream, alerts, cases and the audit log.

Every JSON body carries both statements. Every customer level view, case action and
score request writes its audit row and commits it before the payload is built, so a
response can never exist without its audit record. Endpoints that touch customer
level data, cases or scores sit behind a bearer token; this is a demonstration and
the README says a token is all the authentication there is.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any

import polars as pl
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from ledger_core.statements import statements_payload
from ledger_desk.replay import Event, LabelBook, ReplayWorker
from ledger_desk.rules import load_rules
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select
from starlette.exceptions import HTTPException as StarletteHTTPException

from ledger_api.db import Alert, AuditEntry, Case, CaseEvent, ScoreDecision, create_all, make_engine, now
from ledger_api.scoring import FraudService, ScorecardService, digest
from ledger_api.settings import Settings, load_settings

DISPOSITIONS = {"closed_no_action", "escalated_for_sar_review", "kept_open"}
STATUSES = {"open", "escalated", "closed"}


def envelope(data: dict[str, Any]) -> dict[str, Any]:
    return {"statements": statements_payload(), **data}


class ScorecardRequest(BaseModel):
    applicant: dict[str, Any]


class ScoreRequest(BaseModel):
    features: dict[str, Any]


class CaseOpen(BaseModel):
    alert_id: int
    assignee: str | None = None
    note: str = Field(default="", max_length=2000)


class CaseUpdate(BaseModel):
    status: str | None = None
    assignee: str | None = None
    disposition: str | None = None
    note: str = Field(default="", max_length=2000)


@dataclass
class AppState:
    settings: Settings
    engine: Any
    scorecard: ScorecardService | None = None
    fraud: FraudService | None = None
    worker: ReplayWorker | None = None
    worker_task: asyncio.Task[int] | None = None
    registry: dict[str, Any] = field(default_factory=dict)


def build_worker(
    settings: Settings, engine: Any, chargeback_days: int = 60, *, loop_forever: bool = True
) -> ReplayWorker | None:
    stream_path = settings.replay_file
    history_path = stream_path.with_name("replay_history.parquet")
    if not stream_path.exists():
        return None
    stream = pl.read_parquet(stream_path)
    parts = [
        stream.select(
            "transaction_time", declined=pl.col("decision") == "decline", is_fraud=pl.col("is_fraud")
        )
    ]
    if history_path.exists():
        parts.insert(0, pl.read_parquet(history_path))
    book = pl.concat(parts).sort("transaction_time")
    labels = LabelBook(
        times=book["transaction_time"].to_numpy(),
        declined=book["declined"].to_numpy(),
        fraud=book["is_fraud"].to_numpy(),
        chargeback_days=chargeback_days,
    )
    rules = load_rules(settings.rules)

    async def persist(event: Event) -> None:
        await asyncio.to_thread(persist_alert, engine, event)

    return ReplayWorker(
        stream=stream,
        seconds_per_hour=settings.replay_seconds_per_hour,
        rule_statements=rules.statements,
        labels=labels,
        on_alert=persist,
        loop_forever=loop_forever,
    )


def persist_alert(engine: Any, event: Event) -> None:
    with Session(engine) as session:
        exists = session.exec(select(Alert).where(Alert.txn_id == event["txn_id"])).first()
        if exists is not None:
            return
        session.add(
            Alert(
                txn_id=event["txn_id"],
                # The stream carries the card network's wall clock time; it is stored as UTC.
                transaction_time=datetime.fromisoformat(event["time"]).replace(tzinfo=UTC),
                card_key=event["card"],
                category=event["category"],
                amount=event["amount"],
                score=event["score"],
                decision=event["decision"],
                queue=event["queue"],
                rules=event["rules"],
                model_reasons=event["reasons"],
            )
        )
        session.commit()


def state_of(request: Request) -> AppState:
    state: AppState = request.app.state.ledger
    return state


def session_of(request: Request) -> Iterator[Session]:
    with Session(state_of(request).engine) as session:
        yield session


def actor(request: Request) -> str:
    cfg_ = state_of(request).settings
    header = request.headers.get("authorization", "")
    if cfg_.token_required and header != f"Bearer {cfg_.api_token}":
        raise HTTPException(status_code=401, detail="a bearer token is required for this endpoint")
    return request.headers.get("x-ledger-actor", "desk_analyst")


SessionDep = Annotated[Session, Depends(session_of)]
ActorDep = Annotated[str, Depends(actor)]


def create_app(settings: Settings | None = None, *, start_desk: bool = True) -> FastAPI:
    cfg = settings or load_settings()
    engine = make_engine(cfg.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        create_all(engine)
        state: AppState = app.state.ledger
        registry = cfg.results / "models" / "registry.json"
        state.registry = json.loads(registry.read_text()) if registry.exists() else {}
        if (cfg.results / "models" / "pd_scorecard" / "scorecard_generated.json").exists():
            state.scorecard = ScorecardService.load(cfg.results, cfg.rules)
        if (cfg.results / "models" / "fraud_card" / "serving.json").exists():
            state.fraud = FraudService.load(cfg.results)
        state.worker = build_worker(cfg, engine, loop_forever=cfg.replay_loop)
        if start_desk and state.worker is not None:
            state.worker_task = asyncio.create_task(state.worker.run())
        yield
        if state.worker_task is not None:
            state.worker_task.cancel()

    app = FastAPI(title="ledger", version="0.1.0", lifespan=lifespan)
    app.state.ledger = AppState(settings=cfg, engine=engine)
    if cfg.cors_origins:
        # The static site lives on another origin; only the origins named in the settings may call.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cfg.cors_origins),
            allow_methods=["GET", "POST", "PATCH"],
            allow_headers=["authorization", "content-type", "x-ledger-actor"],
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=envelope({"error": exc.detail}))

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=envelope({"error": "invalid request", "detail": jsonable_encoder(exc.errors())}),
        )

    def audit(
        session: Session,
        who: str,
        action: str,
        resource: str,
        resource_id: str = "",
        detail: dict[str, Any] | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            actor=who, action=action, resource=resource, resource_id=resource_id, detail=detail or {}
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry

    @app.get("/v1/health")
    def health(request: Request) -> dict[str, Any]:
        state = state_of(request)
        return envelope(
            {
                "status": "ok",
                "scorecard_loaded": state.scorecard is not None,
                "fraud_model_loaded": state.fraud is not None,
                "desk": {
                    "loaded": state.worker is not None,
                    "running": bool(state.worker and state.worker.running),
                },
            }
        )

    @app.get("/v1/registry")
    def registry(request: Request) -> dict[str, Any]:
        return envelope({"models": list(state_of(request).registry.values())})

    @app.post("/v1/scorecard/score")
    def scorecard_score(
        body: ScorecardRequest, request: Request, session: SessionDep, who: ActorDep
    ) -> dict[str, Any]:
        service = state_of(request).scorecard
        if service is None:
            raise HTTPException(status_code=503, detail="the scorecard has not been built")
        try:
            result = service.score(body.applicant)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        key = digest(body.applicant)
        audit(session, who, "score", "pd_scorecard", key, {"decision": result["decision"]})
        session.add(
            ScoreDecision(
                model_id="pd_scorecard",
                request_digest=key,
                score=result["score"],
                probability=result["probability_of_default"],
                decision=result["decision"],
                reasons=result["reasons"],
            )
        )
        session.commit()
        return envelope({"model": "pd_scorecard", **result})

    @app.post("/v1/score/{model_id}")
    def score(
        model_id: str, body: ScoreRequest, request: Request, session: SessionDep, who: ActorDep
    ) -> dict[str, Any]:
        state = state_of(request)
        key = digest(body.features)
        if model_id == "pd_scorecard":
            if state.scorecard is None:
                raise HTTPException(status_code=503, detail="the scorecard has not been built")
            try:
                result = state.scorecard.score(body.features)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            probability = result["probability_of_default"]
        elif model_id == "fraud_card":
            if state.fraud is None:
                raise HTTPException(status_code=503, detail="the fraud model has not been built")
            try:
                result = state.fraud.score(body.features)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            probability = result["score"]
        else:
            raise HTTPException(status_code=404, detail=f"no served model called {model_id}")
        audit(session, who, "score", model_id, key, {"decision": result["decision"]})
        session.add(
            ScoreDecision(
                model_id=model_id,
                request_digest=key,
                score=float(result["score"]),
                probability=float(probability),
                decision=result["decision"],
                reasons=result.get("reasons", []),
            )
        )
        session.commit()
        return envelope({"model": model_id, **result})

    @app.get("/v1/desk/snapshot")
    def desk_snapshot(request: Request) -> dict[str, Any]:
        worker = state_of(request).worker
        if worker is None:
            raise HTTPException(status_code=503, detail="no scored stream to replay")
        return envelope({"desk": worker.snapshot()})

    @app.get("/v1/desk/stream")
    async def desk_stream(
        request: Request, batch_ms: int = 250, limit: int | None = None
    ) -> StreamingResponse:
        """Server sent events: a hello with the desk's state, then batches of transactions.

        ``limit`` ends the stream after that many messages, for clients and tests that
        want a bounded read.
        """
        worker = state_of(request).worker
        if worker is None:
            raise HTTPException(status_code=503, detail="no scored stream to replay")
        queue = worker.subscribe()

        async def events() -> AsyncIterator[str]:
            try:
                hello = envelope(
                    {
                        "type": "hello",
                        "desk": worker.snapshot(),
                        "replay": True,
                        "note": "A replay of a scored stream at a stated speed, not a message bus.",
                    }
                )
                yield f"event: hello\ndata: {json.dumps(hello)}\n\n"
                sent = 1
                while limit is None or sent < limit:
                    if await request.is_disconnected():
                        break
                    batch: list[Event] = []
                    try:
                        batch.append(await asyncio.wait_for(queue.get(), timeout=batch_ms / 1000))
                        while not queue.empty() and len(batch) < 500:
                            batch.append(queue.get_nowait())
                    except TimeoutError:
                        pass
                    message = envelope({"type": "transactions", "events": batch, "desk": worker.snapshot()})
                    yield f"event: transactions\ndata: {json.dumps(message)}\n\n"
                    sent += 1
            finally:
                worker.unsubscribe(queue)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/v1/desk/alerts")
    def alerts(request: Request, session: SessionDep, who: ActorDep, limit: int = 100) -> dict[str, Any]:
        audit(session, who, "view", "alerts", "", {"limit": limit})
        rows = session.exec(
            select(Alert)
            .where(Alert.status == "open")
            .order_by(col(Alert.queue).desc(), col(Alert.score).desc())
            .limit(min(limit, 500))
        ).all()
        return envelope({"alerts": [r.model_dump(mode="json") for r in rows]})

    @app.post("/v1/cases", status_code=201)
    def open_case(body: CaseOpen, request: Request, session: SessionDep, who: ActorDep) -> dict[str, Any]:
        alert = session.get(Alert, body.alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="no such alert")
        case = Case(alert_id=body.alert_id, assignee=body.assignee)
        session.add(case)
        alert.status = "in_case"
        session.add(alert)
        session.commit()
        session.refresh(case)
        session.add(CaseEvent(case_id=case.id or 0, action="opened", actor=who, note=body.note))
        session.commit()
        audit(session, who, "open", "case", str(case.id), {"alert_id": body.alert_id})
        session.refresh(case)
        return envelope({"case": case.model_dump(mode="json")})

    @app.patch("/v1/cases/{case_id}")
    def update_case(
        case_id: int, body: CaseUpdate, request: Request, session: SessionDep, who: ActorDep
    ) -> dict[str, Any]:
        case = session.get(Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="no such case")
        if body.status is not None and body.status not in STATUSES:
            raise HTTPException(status_code=422, detail=f"status must be one of {sorted(STATUSES)}")
        if body.disposition is not None and body.disposition not in DISPOSITIONS:
            raise HTTPException(status_code=422, detail=f"disposition must be one of {sorted(DISPOSITIONS)}")
        changes = body.model_dump(exclude_none=True, exclude={"note"})
        for key, value in changes.items():
            setattr(case, key, value)
        case.updated_at = now()
        session.add(case)
        session.add(
            CaseEvent(
                case_id=case_id,
                action="updated:" + ",".join(sorted(changes)) if changes else "note",
                actor=who,
                note=body.note,
            )
        )
        session.commit()
        session.refresh(case)
        audit(session, who, "update", "case", str(case_id), changes)
        session.refresh(case)
        return envelope({"case": case.model_dump(mode="json")})

    @app.get("/v1/cases")
    def list_cases(request: Request, session: SessionDep, who: ActorDep) -> dict[str, Any]:
        audit(session, who, "view", "cases")
        rows = session.exec(select(Case).order_by(col(Case.updated_at).desc()).limit(200)).all()
        return envelope({"cases": [r.model_dump(mode="json") for r in rows]})

    @app.get("/v1/cases/{case_id}")
    def get_case(case_id: int, request: Request, session: SessionDep, who: ActorDep) -> dict[str, Any]:
        audit(session, who, "view", "case", str(case_id))
        case = session.get(Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="no such case")
        events = session.exec(
            select(CaseEvent).where(CaseEvent.case_id == case_id).order_by(col(CaseEvent.at))
        ).all()
        alert = session.get(Alert, case.alert_id)
        return envelope(
            {
                "case": case.model_dump(mode="json"),
                "events": [e.model_dump(mode="json") for e in events],
                "alert": alert.model_dump(mode="json") if alert else None,
            }
        )

    @app.get("/v1/audit")
    def audit_log(request: Request, session: SessionDep, who: ActorDep, limit: int = 100) -> dict[str, Any]:
        audit(session, who, "view", "audit_log")
        rows = session.exec(
            select(AuditEntry).order_by(col(AuditEntry.id).desc()).limit(min(limit, 500))
        ).all()
        return envelope({"audit": [r.model_dump(mode="json") for r in rows]})

    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=int(__import__("os").environ.get("PORT", "8080")))
