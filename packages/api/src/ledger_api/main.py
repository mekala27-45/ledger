"""ASGI entry point: ``uvicorn ledger_api.main:app``."""

from __future__ import annotations

from ledger_api.app import create_app

app = create_app()
