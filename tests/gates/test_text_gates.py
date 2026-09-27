"""Every gate gets three tests: a clean pass, a deliberate violation, and a refusal on nothing."""

from __future__ import annotations

from pathlib import Path

import pytest
from ledger_core.statements import DEMONSTRATION, NOT_A_DECISION

from scripts import check_no_em_dash, check_statements, check_vocabulary

ROOT = Path(__file__).resolve().parents[2]


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


class TestDashGate:
    def test_clean_files_pass(self, tmp_path: Path) -> None:
        files = [_write(tmp_path, "a.md", "Ranges run from 1 to 5, asides use commas.")]
        assert check_no_em_dash.check(tmp_path, files) == 1

    def test_em_dash_is_caught(self, tmp_path: Path) -> None:
        files = [_write(tmp_path, "a.md", "A pause" + chr(0x2014) + "like this.")]
        with pytest.raises(ValueError, match="em dash"):
            check_no_em_dash.check(tmp_path, files)

    def test_en_dash_is_caught(self, tmp_path: Path) -> None:
        files = [_write(tmp_path, "a.md", "2024" + chr(0x2013) + "2026")]
        with pytest.raises(ValueError, match="en dash"):
            check_no_em_dash.check(tmp_path, files)

    def test_refuses_to_pass_on_nothing(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="no files"):
            check_no_em_dash.check(tmp_path, [])

    def test_repository_is_clean(self) -> None:
        assert check_no_em_dash.check(ROOT) > 10


class TestVocabularyGate:
    def test_plain_prose_passes(self, tmp_path: Path) -> None:
        files = [_write(tmp_path, "a.md", "The scorecard ranks applicants by the odds of default.")]
        assert check_vocabulary.check(tmp_path, files) == 1

    def test_filler_is_caught(self, tmp_path: Path) -> None:
        phrase = "lever" + "aging"
        files = [_write(tmp_path, "a.md", f"We are {phrase} the data.")]
        with pytest.raises(ValueError, match="vocabulary"):
            check_vocabulary.check(tmp_path, files)

    def test_refuses_to_pass_on_nothing(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="no files"):
            check_vocabulary.check(tmp_path, [])

    def test_repository_is_clean(self) -> None:
        assert check_vocabulary.check(ROOT) > 10


class TestStatementsGate:
    def test_both_statements_pass(self, tmp_path: Path) -> None:
        files = [_write(tmp_path, "page.md", f"# Page\n\n{DEMONSTRATION}\n\n{NOT_A_DECISION}\n")]
        assert check_statements.check(tmp_path, files) == 1

    def test_wrapped_statements_pass(self, tmp_path: Path) -> None:
        wrapped = DEMONSTRATION.replace(" ", "\n", 3)
        files = [_write(tmp_path, "page.md", f"{wrapped}\n{NOT_A_DECISION}")]
        assert check_statements.check(tmp_path, files) == 1

    def test_missing_statement_is_caught(self, tmp_path: Path) -> None:
        files = [_write(tmp_path, "page.md", DEMONSTRATION)]
        with pytest.raises(ValueError, match="missing a statement"):
            check_statements.check(tmp_path, files)

    def test_html_is_read_as_visible_text(self, tmp_path: Path) -> None:
        html = f"<footer><p>{DEMONSTRATION}</p><script>'{NOT_A_DECISION}'</script></footer>"
        files = [_write(tmp_path, "index.html", html)]
        with pytest.raises(ValueError, match="missing a statement"):
            check_statements.check(tmp_path, files)

    def test_refuses_to_pass_on_nothing(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="no surfaces"):
            check_statements.check(tmp_path, [])
