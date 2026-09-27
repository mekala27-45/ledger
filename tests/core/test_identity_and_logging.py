from __future__ import annotations

import json

from ledger_core.identity import find_card_numbers, hash_id, luhn_valid
from ledger_core.log import redact
from ledger_core.statements import DEMONSTRATION, NOT_A_DECISION, contains_both, statements_payload


def test_luhn() -> None:
    assert luhn_valid("4111111111111111")
    assert not luhn_valid("4111111111111112")


def test_card_numbers_are_found_with_separators() -> None:
    assert find_card_numbers("paid with 4111-1111-1111-1111 today") == ["4111111111111111"]
    assert find_card_numbers("amount 1234.56 on 2026-08-31, id 20260831") == []


def test_hash_is_salted_and_stable() -> None:
    assert hash_id("C001", "a") == hash_id("C001", "a")
    assert hash_id("C001", "a") != hash_id("C001", "b")
    assert len(hash_id("C001", "a")) == 16


def test_log_events_drop_numbers_and_hash_customers() -> None:
    event = {
        "event": "score",
        "customer_id": "C0001",
        "cc_num": "4111111111111111",
        "note": "card 4111111111111111",
    }
    out = redact(None, "info", dict(event))
    assert "cc_num" not in out
    assert out["customer_id"] != "C0001"
    assert "4111111111111111" not in json.dumps(out)


def test_statements() -> None:
    assert contains_both(DEMONSTRATION + " " + NOT_A_DECISION)
    assert not contains_both(DEMONSTRATION)
    assert set(statements_payload()) == {"demonstration", "not_a_decision"}


def test_the_fraction_of_a_float_is_not_a_card_number() -> None:
    # The digits after the point pass the Luhn check; as a fraction they are not a card.
    assert find_card_numbers('{"nim": 0.4111111111111111, "x": 1.4111111111111111e-05}') == []
    assert find_card_numbers("card 4111111111111111.") == ["4111111111111111"]
