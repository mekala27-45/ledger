"""Both statements on every endpoint, the token gate, scoring, cases and audit, observed independently."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from ledger_api import app as app_module
from ledger_api.app import build_worker, create_app
from ledger_api.settings import Settings
from ledger_core.statements import DEMONSTRATION, NOT_A_DECISION

from tests.api.conftest import auth, fixture_stream, rows

pytestmark = pytest.mark.postgres

DECLINED_APPLICANT = {
    "revolving_utilization": 0.95,
    "bureau_score": 610,
    "dti": 0.55,
    "employment_months": 3,
    "oldest_trade_months": 14,
    "purpose": "other",
    "inquiries_6m": 6,
    "loan_amount": 30000,
}
APPROVED_APPLICANT = {
    "revolving_utilization": 0.05,
    "bureau_score": 800,
    "dti": 0.1,
    "employment_months": 200,
    "oldest_trade_months": 300,
    "purpose": "auto",
    "inquiries_6m": 0,
    "loan_amount": 3000,
}


def _both(body: dict[str, object]) -> None:
    statements = body["statements"]
    assert isinstance(statements, dict)
    assert statements["demonstration"] == DEMONSTRATION
    assert statements["not_a_decision"] == NOT_A_DECISION


def _open_alert(client: TestClient, settings: Settings) -> int:
    worker = build_worker(settings, client.app.state.ledger.engine, loop_forever=False)  # type: ignore[attr-defined]
    assert worker is not None
    asyncio.run(worker.run())
    return int(rows(settings.database_url, "select min(id) from alerts")[0][0])  # type: ignore[call-overload]


def test_every_route_carries_both_statements(client: TestClient, settings: Settings) -> None:
    alert_id = _open_alert(client, settings)
    calls = [
        ("get", "/v1/health", None),
        ("get", "/v1/registry", None),
        ("post", "/v1/scorecard/score", {"applicant": DECLINED_APPLICANT}),
        ("post", "/v1/score/pd_scorecard", {"features": DECLINED_APPLICANT}),
        ("get", "/v1/desk/alerts", None),
        ("post", "/v1/cases", {"alert_id": alert_id, "assignee": "a.analyst"}),
        ("get", "/v1/cases", None),
        ("get", "/v1/audit", None),
        ("get", "/v1/score/nothing", None),  # an error body carries them too
    ]
    for method, path, body in calls:
        response = (
            getattr(client, method)(path, json=body, headers=auth())
            if body
            else getattr(client, method)(path, headers=auth())
        )
        _both(response.json())
    case_id = client.get("/v1/cases", headers=auth()).json()["cases"][0]["id"]
    for method, path, body in [
        ("patch", f"/v1/cases/{case_id}", {"status": "escalated"}),
        ("get", f"/v1/cases/{case_id}", None),
    ]:
        response = (
            getattr(client, method)(path, json=body, headers=auth())
            if body
            else getattr(client, method)(path, headers=auth())
        )
        _both(response.json())
    routes = {r.path for r in client.app.routes if r.path.startswith("/v1/")}  # type: ignore[attr-defined]
    covered = {
        "/v1/health",
        "/v1/registry",
        "/v1/scorecard/score",
        "/v1/score/{model_id}",
        "/v1/desk/alerts",
        "/v1/cases",
        "/v1/cases/{case_id}",
        "/v1/audit",
        "/v1/desk/stream",
        "/v1/desk/snapshot",
    }
    assert routes == covered, routes ^ covered


def test_the_stream_and_snapshot_carry_both_statements(settings: Settings) -> None:
    app = create_app(settings, start_desk=False)
    with TestClient(app) as client:
        _both(client.get("/v1/desk/snapshot").json())
        with client.stream("GET", "/v1/desk/stream?limit=2&batch_ms=50") as response:
            for line in response.iter_lines():
                if line.startswith("data: "):
                    import json

                    _both(json.loads(line[len("data: ") :]))
                    break


def test_the_token_gate(client: TestClient) -> None:
    for method, path in [
        ("post", "/v1/scorecard/score"),
        ("get", "/v1/desk/alerts"),
        ("get", "/v1/cases"),
        ("get", "/v1/audit"),
    ]:
        response = client.post(path, json={"applicant": {}}) if method == "post" else client.get(path)
        assert response.status_code == 401
        _both(response.json())
    assert client.get("/v1/health").status_code == 200


def test_scorecard_reasons_for_a_decline_and_none_for_an_approval(
    client: TestClient, settings: Settings
) -> None:
    declined = client.post(
        "/v1/scorecard/score", json={"applicant": DECLINED_APPLICANT}, headers=auth()
    ).json()
    assert declined["decision"] == "decline"
    assert 1 <= len(declined["reasons"]) <= 4
    approved = client.post(
        "/v1/scorecard/score", json={"applicant": APPROVED_APPLICANT}, headers=auth()
    ).json()
    assert approved["decision"] == "approve" and approved["reasons"] == []
    stored = rows(settings.database_url, "select decision from score_decisions order by id")
    assert [r[0] for r in stored] == ["decline", "approve"]


def test_a_proxy_is_refused_at_the_door(client: TestClient) -> None:
    body = {"applicant": {**APPROVED_APPLICANT, "applicant_age": 44}}
    response = client.post("/v1/scorecard/score", json=body, headers=auth())
    assert response.status_code == 422 and "applicant_age" in response.json()["error"]


def test_case_actions_are_persisted_and_audited_independently(client: TestClient, settings: Settings) -> None:
    alert_id = _open_alert(client, settings)
    opened = client.post(
        "/v1/cases",
        json={"alert_id": alert_id, "assignee": "a.analyst", "note": "card holder called"},
        headers=auth(),
    )
    assert opened.status_code == 201
    case_id = opened.json()["case"]["id"]
    client.patch(
        f"/v1/cases/{case_id}",
        json={"status": "closed", "disposition": "closed_no_action", "note": "genuine"},
        headers=auth(),
    )
    url = settings.database_url
    assert rows(url, f"select status, disposition from cases where id = {case_id}") == [
        ("closed", "closed_no_action")
    ]
    assert rows(url, f"select status from alerts where id = {alert_id}") == [("in_case",)]
    actions = [
        r[0] for r in rows(url, f"select action from case_events where case_id = {case_id} order by id")
    ]
    assert actions == ["opened", "updated:disposition,status"]
    audited = rows(url, "select action, resource, actor from audit_log where resource = 'case' order by id")
    assert audited == [("open", "case", "test_analyst"), ("update", "case", "test_analyst")]


def test_invalid_dispositions_are_refused(client: TestClient, settings: Settings) -> None:
    alert_id = _open_alert(client, settings)
    case_id = client.post("/v1/cases", json={"alert_id": alert_id}, headers=auth()).json()["case"]["id"]
    response = client.patch(f"/v1/cases/{case_id}", json={"disposition": "filed_sar"}, headers=auth())
    assert response.status_code == 422


def test_the_audit_row_exists_before_the_payload_is_built(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _open_alert(client, settings)
    seen: list[int] = []
    real = app_module.envelope

    def observing(data: dict[str, object]) -> dict[str, object]:
        if "alerts" in data or "cases" in data:
            seen.append(
                int(rows(settings.database_url, "select count(*) from audit_log where action = 'view'")[0][0])
            )  # type: ignore[call-overload]
        return real(data)

    monkeypatch.setattr(app_module, "envelope", observing)
    client.get("/v1/desk/alerts", headers=auth())
    client.get("/v1/cases", headers=auth())
    assert seen == [1, 2]


def test_the_stream_emits_the_fixture_in_order_and_persists_exactly_its_alerts(
    client: TestClient, settings: Settings
) -> None:
    worker = build_worker(settings, client.app.state.ledger.engine, loop_forever=False)  # type: ignore[attr-defined]
    assert worker is not None
    queue = worker.subscribe()
    emitted = asyncio.run(worker.run())
    fixture = fixture_stream()
    events = [queue.get_nowait() for _ in range(queue.qsize())]
    assert emitted == fixture.height == len(events)
    assert [e["txn_id"] for e in events] == fixture["txn_id"].to_list()
    assert [e["time"] for e in events] == sorted(e["time"] for e in events)
    expected = set(fixture.filter(fixture["decision"] != "approve")["txn_id"].to_list())
    stored = {r[0] for r in rows(settings.database_url, "select txn_id from alerts")}
    assert stored == expected
