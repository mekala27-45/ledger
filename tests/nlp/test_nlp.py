"""Complaint text: timing, the protected vocabulary, form letters and expected topics."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest
from ledger_nlp.topics import TopicModel, distinct, excerpt, expected_topics, opening, templates
from ledger_nlp.train import TimingError, build, check_timing, text_terms

ROOT = Path(__file__).resolve().parents[2]


def test_fields_written_after_filing_are_refused() -> None:
    check_timing(["consumer_complaint_narrative", "product", "issue"])
    with pytest.raises(TimingError):
        check_timing(["consumer_complaint_narrative", "company_response_to_consumer"])
    with pytest.raises(TimingError):
        check_timing(["company_public_response"])


def test_protected_words_never_reach_the_vocabulary() -> None:
    banned = text_terms(ROOT / "rules")
    assert {"elderly", "veteran", "disabled"} <= set(banned)
    text = "the elderly veteran was charged a fee twice and the bank refused a refund of the fee charge"
    frame = pl.DataFrame(
        {
            "narrative": [text] * 6 + ["the bank charged an overdraft fee on my checking account"] * 6,
            "product": ["Checking or savings account"] * 12,
            "sub_product": [""] * 12,
            "issue": ["Managing an account"] * 12,
            "company": ["A BANK"] * 12,
        }
    )
    vectorizer, _ = build(frame, ROOT / "rules")
    vocab = set(vectorizer.get_feature_names_out())
    assert "refund" in vocab
    assert "elderly" not in vocab and "veteran" not in vocab
    for term in vocab:
        assert not set(term.split()) & set(banned), term


def test_form_letters_are_found_and_counted_once() -> None:
    letter = (
        "This letter serves as a formal request for validation of the alleged debt under 15 U.S.C. 1692g XXXX"
    )
    texts = [letter.replace("XXXX", f"account {i}") for i in range(6)] + [
        "My card was charged twice for one purchase."
    ]
    flags, share = templates(texts, min_copies=5)
    assert flags[:6].all() and not flags[6]
    assert share == pytest.approx(6 / 7)
    assert distinct(texts) == [0, 6]
    assert opening("XXXX 1234 Hello  World") == "hello world"


def test_excerpts_mask_long_numbers() -> None:
    assert "1992" not in excerpt("Born XX/XX/1992 and charged twice")
    assert excerpt("short") == "short"


def test_expected_themes_need_two_marker_words() -> None:
    model = TopicModel(
        terms=[
            ["debt", "collection", "letter"],
            ["fraud", "card", "bank"],
            ["fraud", "unauthorized", "stolen"],
        ],
        weights=np.zeros((1, 3)),
        labels=["a", "b", "c"],
        vectorizer=None,  # type: ignore[arg-type]
        nmf=None,  # type: ignore[arg-type]
    )
    found = dict(expected_topics(model))
    assert found["Debt collection contact"] == 0
    assert found["Fraud on an account"] == 2
    assert found["Billing disputes"] is None
