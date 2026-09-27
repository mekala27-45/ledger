"""The two statements that appear on every surface.

Written once here. Pages, API responses, validation reports, the board pack and
the workbook all read them from this module, and a gate checks each surface.
"""

from __future__ import annotations

DEMONSTRATION = (
    "Harborline Bank is fictional. This is a demonstration on generated data and public "
    "datasets; no real customer, account or transaction of any real institution appears here."
)

NOT_A_DECISION = (
    "Nothing here is a credit decision, a fraud determination, a suspicious activity "
    "finding or investment advice."
)

BOTH = (DEMONSTRATION, NOT_A_DECISION)


def statements_markdown() -> str:
    """Both statements as a Markdown block quote, for documents."""
    return f"> {DEMONSTRATION}\n>\n> {NOT_A_DECISION}"


def statements_payload() -> dict[str, str]:
    """Both statements as a JSON-ready mapping, for API response bodies."""
    return {"demonstration": DEMONSTRATION, "not_a_decision": NOT_A_DECISION}


def contains_both(text: str) -> bool:
    """True when both statements appear verbatim, allowing for line wrapping."""
    flat = " ".join(text.split())
    return all(" ".join(s.split()) in flat for s in BOTH)
