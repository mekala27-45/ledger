"""The claim gate renders documents from the manifest and diffs whole files."""

from __future__ import annotations

from pathlib import Path

import pytest
from ledger_core.manifest import Manifest
from ledger_render.render import ClaimGateError, Renderer, Target, hand_typed_numbers
from ledger_render.targets import discover


def _setup(tmp_path: Path) -> tuple[Renderer, Path]:
    templates = tmp_path / "docs" / "templates"
    templates.mkdir(parents=True)
    (templates / "RESULTS.md.j2").write_text(
        "# Results\n\nNet interest margin was {{ v('f01.nim') }}.\n\n{{ table('f02.bins') }}\n\n{{ statements() }}\n"
    )
    manifest = Manifest(as_of="2026-08-31", seed=1)
    manifest.put("f01.nim", 0.0321, "pct2", backend="generated", population="bank", source="mart_ratios")
    manifest.put_table(
        "f02.bins",
        ["bin", "woe"],
        ["text", "float3"],
        [["low", -0.4], ["high", 0.61]],
        backend="generated",
        population="booked",
        source="scorecard",
    )
    renderer = Renderer(tmp_path, manifest, discover(tmp_path), [templates])
    return renderer, tmp_path / "RESULTS.md"


def test_clean_render_passes(tmp_path: Path) -> None:
    renderer, out = _setup(tmp_path)
    renderer.write_all()
    assert "3.21%" in out.read_text()
    assert renderer.check_all() == []


def test_a_number_edited_by_hand_is_caught(tmp_path: Path) -> None:
    renderer, out = _setup(tmp_path)
    renderer.write_all()
    out.write_text(out.read_text().replace("3.21%", "3.40%"))
    drifts = renderer.check_all()
    assert len(drifts) == 1
    assert "-Net interest margin was 3.40%." in drifts[0].diff
    assert "+Net interest margin was 3.21%." in drifts[0].diff


def test_a_missing_document_is_caught(tmp_path: Path) -> None:
    renderer, _ = _setup(tmp_path)
    assert renderer.check_all()[0].output == "RESULTS.md"


def test_refuses_with_no_documents(tmp_path: Path) -> None:
    manifest = Manifest(as_of="2026-08-31", seed=1)
    manifest.put("a.b", 1, "int", backend="static", population="p", source="s")
    with pytest.raises(ClaimGateError, match="no documents"):
        Renderer(tmp_path, manifest, [], [tmp_path])


def test_refuses_with_an_empty_manifest(tmp_path: Path) -> None:
    with pytest.raises(ClaimGateError, match="empty manifest"):
        Renderer(tmp_path, Manifest(as_of="2026-08-31", seed=1), [Target("a.j2", "a.md")], [tmp_path])


def test_unknown_key_fails_loudly(tmp_path: Path) -> None:
    renderer, _ = _setup(tmp_path)
    (tmp_path / "docs" / "templates" / "RESULTS.md.j2").write_text("{{ v('f09.nothing') }}")
    with pytest.raises(KeyError):
        renderer.write_all()


def test_hand_typed_numbers_are_found_outside_expressions() -> None:
    text = "Gini was {{ v('f02.gini') }} and precision was 0.81 under SR 11-7."
    assert hand_typed_numbers(text, ["SR 11-7"]) == ["0.81"]
    assert hand_typed_numbers("{{ v('a.b') }} only", []) == []


def test_partials_are_not_rendered_on_their_own(tmp_path: Path) -> None:
    templates = tmp_path / "report" / "templates" / "validation"
    templates.mkdir(parents=True)
    (templates / "_report.md.j2").write_text("x")
    (templates / "pd_scorecard.md.j2").write_text("{% include 'validation/_report.md.j2' %}")
    targets = discover(tmp_path)
    assert [t.output for t in targets] == ["report/validation/pd_scorecard.md"]
