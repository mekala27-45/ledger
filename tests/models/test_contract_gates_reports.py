"""The model contract, promotion gates, the challenge log and the validation report's refusal."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from ledger_core.manifest import Manifest
from ledger_models.contract import CONTRACT_LINES, ModelCard, tier_for
from ledger_models.evaluate import EvaluationError, discrimination, recall_at_fpr, reliability
from ledger_models.gates import Gate, GateError, conclusion, run_gates
from ledger_models.report import ModelResult, put_result, read_challenges
from ledger_render.render import ClaimGateError, Renderer, Target

ROOT = Path(__file__).resolve().parents[2]


def _card(**overrides: object) -> ModelCard:
    base: dict[str, object] = dict(
        model_id="m",
        function="f02",
        title="t",
        purpose="p",
        tier=1,
        tier_reason="r",
        role="champion",
        status="in use",
        prediction_time="now",
        outcome="o",
        population="pop",
        backend="generated",
        method="x",
        features=["a"],
        lines={line: "filled" for line in CONTRACT_LINES},
    )
    base.update(overrides)
    return ModelCard(**base)  # type: ignore[arg-type]


def test_a_card_with_every_line_filled_registers() -> None:
    assert _card().model_id == "m"


def test_a_card_with_a_line_empty_is_refused() -> None:
    lines = {line: "filled" for line in CONTRACT_LINES}
    lines["validated"] = ""
    with pytest.raises(ValueError, match="validated"):
        _card(lines=lines)


def test_a_card_with_an_unknown_line_is_refused() -> None:
    lines = {line: "filled" for line in CONTRACT_LINES} | {"vibes": "good"}
    with pytest.raises(ValueError, match="vibes"):
        _card(lines=lines)


def test_tier_rule() -> None:
    assert tier_for(decides_automatically=True, informs_person=False, complex_method=False)[0] == 1
    assert tier_for(decides_automatically=False, informs_person=True, complex_method=True)[0] == 1
    assert tier_for(decides_automatically=False, informs_person=True, complex_method=False)[0] == 2
    assert tier_for(decides_automatically=False, informs_person=False, complex_method=False)[0] == 3


@pytest.mark.parametrize(
    ("gate", "good", "bad"),
    [
        (Gate("a", "AUROC floor", "at_least", 0.7), 0.71, 0.69),
        (Gate("p", "PSI ceiling", "at_most", 0.25), 0.1, 0.3),
        (Gate("r", "ratio band", "between", 0.8, upper=1.25), 1.0, 1.3),
    ],
)
def test_every_gate_passes_and_fails_deliberately(gate: Gate, good: float, bad: float) -> None:
    assert gate.check(good).passed
    assert not gate.check(bad).passed
    assert not gate.check(None).passed


def test_gates_refuse_nothing_and_unmeasured() -> None:
    with pytest.raises(GateError):
        run_gates([], {})
    with pytest.raises(GateError, match="no measurement"):
        run_gates([Gate("a", "x", "at_least", 1.0)], {})


def test_conclusions() -> None:
    critical = Gate("a", "critical gate", "at_least", 1.0)
    soft = Gate("b", "soft gate", "at_least", 1.0, critical=False)
    assert conclusion(run_gates([critical, soft], {"a": 2.0, "b": 2.0}))[0] == "approved"
    verdict, conditions = conclusion(run_gates([critical, soft], {"a": 2.0, "b": 0.0}))
    assert verdict == "approved with conditions" and "soft gate" in conditions[0]
    assert conclusion(run_gates([critical, soft], {"a": 0.0, "b": 2.0}))[0] == "not approved"


def test_challenge_log_is_parsed_and_incomplete_entries_refused(tmp_path: Path) -> None:
    good = tmp_path / "D.md"
    good.write_text(
        "# Decisions\n\n## 2026-09-26: Challenge (m, n): why\n\n**Raised:** a\ncontinued\n\n**Response:** b\n\n"
        "**Changed:** c\n\n## 2026-09-26: Something else\n\ntext\n"
    )
    (c,) = read_challenges(good)
    assert c.models == ("m", "n") and c.raised == "a continued" and c.changed == "c"
    bad = tmp_path / "E.md"
    bad.write_text("## 2026-09-26: Challenge (m): why\n\n**Raised:** a\n\n**Response:** b\n")
    with pytest.raises(ValueError, match="missing"):
        read_challenges(bad)


def test_every_trained_model_has_two_challenges_on_record() -> None:
    challenges = read_challenges(ROOT / "DECISIONS.md")
    for model in ("pd_scorecard", "pd_challenger"):
        assert sum(model in c.models for c in challenges) >= 2


def _result() -> ModelResult:
    rng = np.random.default_rng(0)
    y = (rng.random(400) < 0.2).astype(float)
    p = np.clip(0.2 + 0.3 * (y - 0.2) + rng.normal(0, 0.1, 400), 0.01, 0.99)
    d = discrimination(y, p)
    return ModelResult(
        card=_card(model_id="m"),
        samples={"development": d, "validation": d, "test": d},
        baselines={"Base": d},
        gates=run_gates([Gate("a", "x", "at_least", 0.5)], {"a": d.auroc}),
        reliability=reliability(y, p),
    )


def test_a_model_needs_two_challenges_before_its_report_exists(tmp_path: Path) -> None:
    log = tmp_path / "D.md"
    log.write_text(
        "## 2026-09-26: Challenge (m): one\n\n**Raised:** a\n\n**Response:** b\n\n**Changed:** c\n"
    )
    with pytest.raises(ValueError, match="at least two"):
        put_result(Manifest(as_of="2026-08-31", seed=1), _result(), read_challenges(log))


def test_a_validation_report_refuses_to_render_with_a_section_missing(tmp_path: Path) -> None:
    log = tmp_path / "D.md"
    entry = "## 2026-09-26: Challenge (m): q{i}\n\n**Raised:** a\n\n**Response:** b\n\n**Changed:** c\n\n"
    log.write_text(entry.format(i=1) + entry.format(i=2))
    m = Manifest(as_of="2026-08-31", seed=1)
    put_result(m, _result(), read_challenges(log))
    templates = tmp_path / "templates"
    (templates / "validation").mkdir(parents=True)
    shared = (ROOT / "report" / "templates" / "validation" / "_report.md.j2").read_text()
    (templates / "validation" / "_report.md.j2").write_text(shared)
    sections = [
        "purpose",
        "soundness",
        "data",
        "development",
        "outcomes",
        "benchmarking",
        "limitations",
        "monitoring",
        "challenge",
        "conclusion",
    ]
    complete = "{% set model = 'm' %}\n" + "".join(f"{{% set {s} %}}text{{% endset %}}\n" for s in sections)
    complete += '{% include "validation/_report.md.j2" %}\n'
    (templates / "validation" / "m.md.j2").write_text(complete)
    renderer = Renderer(tmp_path, m, [Target("validation/m.md.j2", "report/validation/m.md")], [templates])
    assert "## Limitations" in renderer.render(renderer.targets[0])
    (templates / "validation" / "m.md.j2").write_text(
        complete.replace("{% set limitations %}text{% endset %}\n", "")
    )
    renderer = Renderer(tmp_path, m, [Target("validation/m.md.j2", "report/validation/m.md")], [templates])
    with pytest.raises(ClaimGateError, match="limitations"):
        renderer.render(renderer.targets[0])


def test_evaluation_refusals_and_the_baf_measure() -> None:
    with pytest.raises(EvaluationError):
        discrimination(np.array([]), np.array([]))
    with pytest.raises(EvaluationError):
        discrimination(np.zeros(10), np.linspace(0, 1, 10))
    y = np.array([0] * 95 + [1] * 5, dtype=float)
    p = np.concatenate([np.linspace(0, 0.5, 95), np.array([0.99, 0.98, 0.97, 0.2, 0.1])])
    recall, threshold = recall_at_fpr(y, p, 0.05)
    assert recall == pytest.approx(0.6) and 0.4 < threshold < 0.5


def test_no_model_in_the_manifest_uses_a_protected_attribute_or_proxy() -> None:
    from ledger_scorecard.policy_files import load_proxies

    proxies = load_proxies(ROOT / "rules")
    manifest = Manifest.load(ROOT / "results" / "manifest.json")
    feature_lists = {
        k: v.value for k, v in manifest.values.items() if k.startswith("models.") and k.endswith(".features")
    }
    assert feature_lists, "no model feature lists in the manifest"
    for key, value in feature_lists.items():
        features = {f.strip().lower() for f in str(value).split(",")}
        assert not features & proxies, (key, features & proxies)


def test_predictive_equality_as_the_suite_defines_it() -> None:
    from ledger_models.evaluate import predictive_equality

    # Ten genuine applicants in each group and one fraud each. At 0.5 the older group has
    # four false positives and the younger one, so the rates are 0.4 and 0.1.
    older = np.array([True] * 11 + [False] * 11)
    y = np.array([0.0] * 10 + [1.0] + [0.0] * 10 + [1.0])
    p = np.array([0.9, 0.8, 0.7, 0.6] + [0.1] * 6 + [0.9] + [0.9] + [0.1] * 9 + [0.9])
    fpr_old, fpr_young, ratio = predictive_equality(y, p, older, 0.5)
    assert (fpr_old, fpr_young) == pytest.approx((0.4, 0.1))
    assert ratio == pytest.approx(0.25)
    # The ratio is symmetric in which group is marked, and one is parity.
    assert predictive_equality(y, p, ~older, 0.5)[2] == pytest.approx(0.25)
    assert predictive_equality(y, np.zeros_like(p), older, 0.5)[2] == 1.0
    with pytest.raises(EvaluationError):
        predictive_equality(y, p, np.ones_like(older), 0.5)


def test_the_baf_protocol_keeps_a_threshold_it_is_given() -> None:
    from ledger_models.train_baf import protocol

    rng = np.random.default_rng(3)
    y = (rng.random(4000) < 0.05).astype(float)
    p = np.clip(rng.normal(0.2 + 0.4 * y, 0.15), 0, 1)
    older = rng.random(4000) < 0.3
    chosen = protocol(y, p, older)
    # With no threshold the suite's rule sets it at a five percent false positive rate.
    assert chosen["fpr"] == pytest.approx(0.05, abs=0.002)
    # A threshold fixed elsewhere is used as given, never re-chosen on these rows.
    fixed = protocol(y, p, older, threshold=0.5)
    assert fixed["threshold"] == 0.5
    assert fixed["recall"] == pytest.approx(float((p[y == 1] >= 0.5).mean()))
