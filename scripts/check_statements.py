"""Both statements on every surface: documents, reports and every page of the built site.

API response bodies are covered by tests/api/test_statements_on_every_endpoint.py,
which walks the route table rather than a hand kept list.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger_core.statements import contains_both

DOCUMENTS = ("README.md", "RESULTS.md", "report/board-pack.md", "report/board-pack.html")
GLOBS = ("report/validation/*.md", "web/out/**/*.html")


def surfaces(root: Path) -> list[Path]:
    found = [root / doc for doc in DOCUMENTS if (root / doc).exists()]
    for pattern in GLOBS:
        found.extend(sorted(root.glob(pattern)))
    return found


def check(root: Path, files: list[Path] | None = None) -> int:
    targets = files if files is not None else surfaces(root)
    targets = list(dict.fromkeys(targets))
    if not targets:
        raise ValueError("the statements gate found no surfaces to check")
    missing = [str(p.relative_to(root)) for p in targets if not contains_both(_visible_text(p))]
    if missing:
        raise ValueError("these surfaces are missing a statement:\n" + "\n".join(missing))
    return len(targets)


def _visible_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".html":
        import html
        import re

        text = re.sub(r"<script.*?</script>", " ", text, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
    return text


if __name__ == "__main__":
    count = check(Path(__file__).resolve().parents[1])
    print(f"statements gate: both statements present on {count} surfaces")
