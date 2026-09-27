"""Identifier hygiene: salted hashing of customer ids and card number detection.

Logs never carry a raw customer id or anything shaped like a card number. The
salt is per deployment; the development default is public on purpose and the
API refuses to start in production mode without its own.
"""

from __future__ import annotations

import hashlib
import os
import re

DEV_SALT = "ledger-development-salt"

_PAN_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


def id_salt() -> str:
    return os.environ.get("LEDGER_ID_SALT", DEV_SALT)


def hash_id(value: str | int, salt: str | None = None) -> str:
    digest = hashlib.sha256(f"{salt or id_salt()}:{value}".encode()).hexdigest()
    return digest[:16]


def luhn_valid(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        number = int(char)
        if position % 2 == 1:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def find_card_numbers(text: str) -> list[str]:
    """Digit runs of 13 to 19 digits (spaces or dashes allowed) that pass the Luhn check."""
    found: list[str] = []
    for match in _PAN_CANDIDATE.finditer(text):
        digits = re.sub(r"[ -]", "", match.group(0))
        if 13 <= len(digits) <= 19 and len(set(digits)) > 1 and luhn_valid(digits):
            found.append(digits)
    return found
