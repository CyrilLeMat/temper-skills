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


def test_canonical_dogfood_tree_passes_its_validation_set():
    """Pins the shipped example tree in CI — the H1 payoff on our own repo."""
    fn = fn_from_json(str(DOGFOOD / "output" / "dog_food_tree.json"))
    data = json.loads((DOGFOOD / "ratified" / "validation_set.json").read_text())
    r = run_validation(fn, data, label_match)
    assert r.passed(1.0), [(d.input, d.expected, d.predicted) for d in r.disagreements]


def test_canonical_ticket_tree_passes_its_validation_set():
    base = REPO / "examples" / "ticket_routing"
    fn = fn_from_json(str(base / "output" / "route_ticket_tree.json"))
    data = load_dataset(str(base / "input" / "validation_set.json"))
    r = run_validation(fn, data, exact_match)
    assert r.passed(1.0), [(d.input, d.expected, d.predicted) for d in r.disagreements]


def test_canonical_license_tree_passes_its_validation_set():
    base = REPO / "examples" / "license_compat"
    fn = fn_from_json(str(base / "output" / "license_tree.json"))
    data = load_dataset(str(base / "input" / "validation_set.json"))
    r = run_validation(fn, data, exact_match)
    assert r.passed(1.0), [(d.input, d.expected, d.predicted) for d in r.disagreements]


def test_canonical_ankle_tree_passes_its_validation_set():
    base = REPO / "examples" / "ankle_sprain"
    fn = fn_from_json(str(base / "output" / "ankle_tree.json"))
    data = load_dataset(str(base / "input" / "validation_set.json"))
    r = run_validation(fn, data, exact_match)
    assert r.passed(1.0), [(d.input, d.expected, d.predicted) for d in r.disagreements]
