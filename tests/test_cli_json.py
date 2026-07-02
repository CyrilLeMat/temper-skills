"""The --json result manifest the agent / pipeline path reads off stdout."""

from __future__ import annotations

from types import SimpleNamespace

from temper_skills.pipelines import tree_manifest as _tree_manifest
from temper_skills.tree import DecisionNode, DecisionTree


def _tree():
    return DecisionTree(
        nodes=[
            DecisionNode(condition='food_item == "chocolate"', outcome="toxic",
                         rounds_survived=12, sources=["domain_expert"]),
            DecisionNode(condition='food_item == "macadamia"', outcome="toxic",
                         gray_zone="skill never lists nuts"),
        ],
        default_outcome="unknown",
        features=["food_item", "preparation"],
        fn_name="can_dog_eat",
        model="vertex_ai/claude-sonnet-4-6 via api",
        profile="quick",
        proposed_examples=[
            {"input": {"food_item": "grape"}, "expected": "toxic",
             "tree_prediction": "toxic", "rationale": "r"},
        ],
    )


def test_manifest_core_fields():
    m = _tree_manifest(_tree(), "out/x.py", "out/x.tempered.md")
    assert m["fn_name"] == "can_dog_eat"
    assert m["tree_path"] == "out/x.py"
    assert m["tempered_skill_path"] == "out/x.tempered.md"
    assert m["features"] == ["food_item", "preparation"]
    assert m["node_count"] == 2
    assert m["profile"] == "quick"
    assert m["generated_at"]  # mandatory for an auditable tree


def test_manifest_extracts_gray_zones():
    m = _tree_manifest(_tree(), "out/x.py", "out/x.tempered.md")
    assert m["gray_zones"] == [
        {"node": 2, "condition": 'food_item == "macadamia"', "note": "skill never lists nuts"}
    ]


def test_manifest_validation_dataset_path_tracks_tree_path():
    m = _tree_manifest(_tree(), "out/x.py", "out/x.tempered.md")
    assert m["validation_case_count"] == 1
    assert m["validation_dataset_path"] == "out/x.validation.jsonl"


def test_manifest_omits_dataset_path_when_none():
    t = _tree()
    t.proposed_examples = None
    m = _tree_manifest(t, "out/x.py", "out/x.tempered.md")
    assert m["validation_dataset_path"] is None
    assert m["validation_case_count"] == 0


def test_manifest_summarizes_ratified_examples():
    t = _tree()
    d = SimpleNamespace(input={"food_item": "x"}, expected="safe", predicted="toxic")
    t.example_report = SimpleNamespace(agreements=3, total=4, disagreements=[d])
    m = _tree_manifest(t, "out/x.py", "out/x.tempered.md")
    assert m["ratified_examples"]["agreements"] == 3
    assert m["ratified_examples"]["total"] == 4
    assert m["ratified_examples"]["disagreements"][0]["predicted"] == "toxic"


def test_manifest_ratified_examples_none_when_unchecked():
    m = _tree_manifest(_tree(), "out/x.py", "out/x.tempered.md")
    assert m["ratified_examples"] is None


def test_manifest_surfaces_loop_error():
    t = _tree()
    m = _tree_manifest(t, "out/x.py", "out/x.tempered.md")
    assert m["loop_error"] is None            # clean run
    t.loop_error = "round 3: RuntimeError: backend fell over"
    m = _tree_manifest(t, "out/x.py", "out/x.tempered.md")
    assert "round 3" in m["loop_error"]       # an agent must not read this as converged
