"""The out of process check: start the API, read the desk stream, act on a case, read it back elsewhere.

Run by CI against a Postgres service, and locally against any reachable database:

    DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5433/ledger_test uv run python scripts/api_smoke.py

1. Starts the API with uvicorn in a child process, replaying a small scored stream
   at full speed.
2. Subscribes to /v1/desk/stream and reads a stated number of events.
3. Opens a case on the first alert and closes it with a disposition.
4. In a separate Python process with a fresh database connection, reads back the
   alert, the case, its events and the audit rows, and exits non zero on any miss.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
EVENTS = 25
TOKEN = "smoke-token-not-a-secret"

READBACK = r"""
import sys, psycopg
url, case_id = sys.argv[1], int(sys.argv[2])
with psycopg.connect(url) as conn, conn.cursor() as cur:
    cur.execute("select count(*) from alerts"); alerts = cur.fetchone()[0]
    cur.execute("select status, disposition from cases where id = %s", (case_id,)); case = cur.fetchone()
    cur.execute("select action from case_events where case_id = %s order by id", (case_id,)); events = [r[0] for r in cur.fetchall()]
    cur.execute("select action, resource from audit_log where resource = 'case' order by id"); audit = cur.fetchall()
ok = alerts > 0 and case == ("closed", "closed_no_action") and events[0] == "opened" and ("open", "case") in audit and ("update", "case") in audit
print({"alerts": alerts, "case": case, "events": events, "audit": audit})
sys.exit(0 if ok else 1)
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def fixture_stream(path: Path) -> None:
    from ledger_desk.fixtures import sample_stream

    sample_stream(60).write_parquet(path)


def main() -> int:
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5433/ledger_test")
    plain = url.replace("postgresql+psycopg://", "postgresql://")
    import psycopg

    with psycopg.connect(plain, autocommit=True) as conn:
        for table in ("case_events", "cases", "score_decisions", "audit_log", "alerts"):
            conn.execute(f"drop table if exists {table} cascade")
    work = Path(tempfile.mkdtemp())
    stream = work / "replay_stream.parquet"
    fixture_stream(stream)
    port = free_port()
    env = dict(
        os.environ,
        DATABASE_URL=url,
        LEDGER_API_TOKEN=TOKEN,
        LEDGER_REPLAY_FILE=str(stream),
        LEDGER_REPLAY_SECONDS_PER_HOUR="2",
        LEDGER_REPLAY_LOOP="0",
        LEDGER_ROOT=str(ROOT),
    )
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "ledger_api.main:app", "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    headers = {"authorization": f"Bearer {TOKEN}", "x-ledger-actor": "smoke"}
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{base}/v1/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        seen: list[dict[str, object]] = []
        with httpx.stream(
            "GET", f"{base}/v1/desk/stream", params={"limit": 400, "batch_ms": 50}, timeout=30
        ) as response:
            for line in response.iter_lines():
                if line.startswith("data: "):
                    message = json.loads(line[6:])
                    assert "statements" in message
                    seen.extend(message.get("events", []))
                    if len(seen) >= EVENTS:
                        break
        in_order = [e["time"] for e in seen] == sorted(e["time"] for e in seen)
        print(f"stream: {len(seen)} events, in time order: {in_order}")
        if len(seen) < EVENTS or not in_order:
            return 1
        alerts = httpx.get(f"{base}/v1/desk/alerts", headers=headers, timeout=10).json()["alerts"]
        if not alerts:
            print("no alerts were persisted")
            return 1
        case = httpx.post(
            f"{base}/v1/cases",
            json={"alert_id": alerts[0]["id"], "assignee": "smoke"},
            headers=headers,
            timeout=10,
        ).json()["case"]
        httpx.patch(
            f"{base}/v1/cases/{case['id']}",
            json={"status": "closed", "disposition": "closed_no_action"},
            headers=headers,
            timeout=10,
        )
    finally:
        server.terminate()
        server.wait(timeout=10)
    check = subprocess.run(
        [sys.executable, "-c", READBACK, plain, str(case["id"])], capture_output=True, text=True
    )
    print(check.stdout.strip() or check.stderr.strip())
    return check.returncode


if __name__ == "__main__":
    sys.exit(main())
