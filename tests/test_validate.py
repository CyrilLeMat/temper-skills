"""Validation harness: agreement accounting, comparators, loaders, CI pin."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from temper_skills.tree import DecisionNode, DecisionTree
from temper_skills.validate import (
    exact_match,
    fn_from_json,
    fn_from_pyfile,
    fn_from_tree,
    label_match,
    load_dataset,
    run_validation,
)

REPO = Path(__file__).resolve().parents[1]
DOGFOOD = REPO / "examples" / "dog_food"


def _tree():
    return DecisionTree(
        nodes=[DecisionNode('food_item == "chocolate"', "no — toxic", sources=["c#1"])],
        default_outcome="yes — safe",
        features=["food_item"],
        fn_name="check",
    )


def test_all_agree():
    fn = fn_from_tree(_tree())
    data = [{"input": {"food_item": "chocolate"}, "expected": "no — toxic"},
            {"input": {"food_item": "carrot"}, "expected": "yes — safe"}]
    r = run_validation(fn, data, exact_match)
    assert r.total == 2 and r.agreements == 2 and r.agreement_rate == 1.0
    assert r.passed()


def test_surfaces_disagreement():
    fn = fn_from_tree(_tree())
    data = [{"input": {"food_item": "carrot"}, "expected": "no — toxic"}]  # wrong label
    r = run_validation(fn, data, exact_match)
    assert r.agreements == 0 and len(r.disagreements) == 1
    d = r.disagreements[0]
    assert d.expected == "no — toxic" and d.predicted == "yes — safe"
    assert not r.passed()


def test_label_vs_exact_match():
    assert label_match("no — toxic, never feed", "no")
    assert not exact_match("no — toxic, never feed", "no")
    assert label_match("escalate_urgent", "escalate_urgent")


def test_crashing_branch_is_a_finding():
    def boom(_):
        raise ValueError("bad branch")

    r = run_validation(boom, [{"input": {}, "expected": "x"}])
    assert r.agreements == 0
    assert r.disagreements[0].predicted.startswith("ERROR: ValueError")


def test_passed_threshold():
    fn = fn_from_tree(_tree())
    data = [{"input": {"food_item": "chocolate"}, "expected": "no — toxic"},
            {"input": {"food_item": "carrot"}, "expected": "WRONG"}]
    r = run_validation(fn, data, exact_match)
    assert r.agreement_rate == 0.5
    assert not r.passed(1.0)
    assert r.passed(0.5)


def test_fn_from_pyfile_single(tmp_path):
    p = tmp_path / "m.py"
    p.write_text("def decide(case):\n    return 'x'\n")
    assert fn_from_pyfile(str(p))({}) == "x"


def test_fn_from_pyfile_ambiguous(tmp_path):
    p = tmp_path / "m.py"
    p.write_text("def a(c): return 1\ndef b(c): return 2\n")
    with pytest.raises(ValueError):
        fn_from_pyfile(str(p))


def test_load_dataset_skips_unratified_proposed_cases(tmp_path):
    """The trust boundary: a machine-proposed label must not gate until ratified."""
    p = tmp_path / "set.json"
    p.write_text(json.dumps([
        {"input": {"x": 1}, "expected": "a"},                       # ratified (no status)
        {"input": {"x": 2}, "expected": "b", "status": "ratified"},  # explicitly ratified
        {"input": {"x": 3}, "expected": "c", "status": "proposed"},  # must be skipped
    ]))
    data = load_dataset(str(p))
    assert [e["input"] for e in data] == [{"x": 1}, {"x": 2}]


def test_load_dataset_reads_jsonl_skill_assets(tmp_path):
    """The skill-dir assets/*.validation.jsonl format must feed the same gate."""
    p = tmp_path / "set.validation.jsonl"
    p.write_text("\n".join([
        json.dumps({"input": {"x": 1}, "expected": "a", "status": "ratified"}),
        "",
        json.dumps({"input": {"x": 2}, "expected": "b", "status": "proposed"}),
    ]))
    data = load_dataset(str(p))
    assert [e["input"] for e in data] == [{"x": 1}]


def _canonical_skill(example: str, skill: str, fn: str):
    """(compiled tree fn, ratified cases) from a committed example Agent Skill dir.

    Trees now live in <skill>/scripts/<fn>.py and the ratified ground truth in
    <skill>/assets/<fn>.validation.jsonl (status: ratified)."""
    base = REPO / "examples" / example / "output" / skill
    tree_fn = fn_from_pyfile(str(base / "scripts" / f"{fn}.py"))
    rows = [json.loads(ln) for ln in (base / "assets" / f"{fn}.validation.jsonl")
            .read_text().splitlines() if ln.strip()]
    data = [{"input": r["input"], "expected": r["expected"]}
            for r in rows if r.get("status") == "ratified"]
    assert data, f"no ratified cases in {example}"
    return tree_fn, data


def test_canonical_dogfood_tree_passes_its_validation_set():
    """Pins the shipped example skill in CI — the H1 payoff on our own repo."""
    fn, data = _canonical_skill("dog_food", "dog-food", "can_dog_eat")
    r = run_validation(fn, data, label_match)
    assert r.passed(1.0), [(d.input, d.expected, d.predicted) for d in r.disagreements]


def test_canonical_ticket_tree_passes_its_validation_set():
    fn, data = _canonical_skill("ticket_routing", "ticket-routing", "route_ticket")
    r = run_validation(fn, data, label_match)
    assert r.passed(1.0), [(d.input, d.expected, d.predicted) for d in r.disagreements]


def test_canonical_license_tree_passes_its_validation_set():
    fn, data = _canonical_skill("license_compat", "license-compat", "assess_license")
    r = run_validation(fn, data, label_match)
    assert r.passed(1.0), [(d.input, d.expected, d.predicted) for d in r.disagreements]


def test_canonical_ankle_tree_passes_its_validation_set():
    fn, data = _canonical_skill("ankle_sprain", "ankle-sprain", "assess_ankle")
    r = run_validation(fn, data, label_match)
    assert r.passed(1.0), [(d.input, d.expected, d.predicted) for d in r.disagreements]


def test_canonical_parking_tree_passes_its_validation_set():
    fn, data = _canonical_skill("parking", "parking", "can_i_park")
    r = run_validation(fn, data, label_match)
    assert r.passed(1.0), [(d.input, d.expected, d.predicted) for d in r.disagreements]
