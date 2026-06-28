"""DecisionTree export: the generated module must compile, run, and carry provenance."""

from __future__ import annotations

from temper_skills.tree import DecisionNode, DecisionTree


def _compile(src: str):
    ns: dict = {}
    exec(compile(src, "<gen>", "exec"), ns)
    return ns


def _tree(**kw):
    nodes = [
        DecisionNode('priority == "high"', "escalate", rounds_survived=14, sources=["constraints#1"]),
        DecisionNode('security_score > 0.8', "secure", rounds_survived=8, sources=["examples#3"],
                     gray_zone="0.7–0.8 ambiguous"),
    ]
    return DecisionTree(nodes=nodes, default_outcome="route_default",
                        features=["priority", "security_score"], fn_name="route", **kw)


def test_generated_code_compiles_and_runs():
    fn = _compile(_tree().to_source())["route"]
    assert fn({"priority": "high", "security_score": 0.1}) == "escalate"
    assert fn({"priority": "low", "security_score": 0.9}) == "secure"
    assert fn({"priority": "low", "security_score": 0.1}) == "route_default"


def test_header_and_provenance_present():
    src = _tree(model="claude-sonnet-4-6", profile="standard").to_source()
    assert "zero LLM calls at inference" in src
    assert "generated_at:" in src and "model: claude-sonnet-4-6" in src
    assert "# n1 — survived 14 rounds — sources: constraints#1" in src
    assert "# gray_zone: 0.7–0.8 ambiguous" in src


def test_features_bound_as_locals():
    src = _tree().to_source()
    assert "priority = case.get('priority')" in src
    assert "security_score = case.get('security_score')" in src


def test_quick_profile_omits_provenance():
    src = _tree(profile="quick", include_provenance=False).to_source()
    assert "draft output, no provenance" in src
    assert "survived" not in src
    assert "gray_zone" not in src
    # still runs
    assert _compile(src)["route"]({"priority": "high", "security_score": 0}) == "escalate"


def test_empty_tree_returns_default():
    t = DecisionTree(nodes=[], default_outcome="unknown", features=["x"], fn_name="d")
    fn = _compile(t.to_source())["d"]
    assert fn({"x": 1}) == "unknown"


def test_export_writes_file(tmp_path):
    out = tmp_path / "route.py"
    _tree().export(str(out))
    assert out.exists()
    fn = _compile(out.read_text())["route"]
    assert fn({"priority": "high", "security_score": 0}) == "escalate"
