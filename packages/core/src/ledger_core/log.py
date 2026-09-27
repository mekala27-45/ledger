"""Structured JSON logging with identifier redaction built in.

Keys that could carry an account or card number are dropped, customer ids are
replaced by a salted hash, and any string value containing a Luhn valid digit
run is masked before the event is written.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

from ledger_core.identity import find_card_numbers, hash_id

FORBIDDEN_KEYS = frozenset(
    {"account_number", "acct_num", "card_number", "cc_num", "pan", "ssn", "routing_number"}
)
HASHED_KEYS = frozenset({"customer_id", "applicant_id", "cust_id"})


def redact(_: Any, __: str, event: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for key in list(event):
        if key in FORBIDDEN_KEYS:
            event.pop(key)
        elif key in HASHED_KEYS and event[key] is not None:
            event[key] = hash_id(str(event[key]))
        elif isinstance(event[key], str) and find_card_numbers(event[key]):
            value = event[key]
            for digits in find_card_numbers(value):
                value = value.replace(digits, "[masked]")
            event[key] = value
    return event


def configure(level: int = logging.INFO) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact,
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)
