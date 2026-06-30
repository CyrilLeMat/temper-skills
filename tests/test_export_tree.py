"""The deterministic JSON -> .py exporter the skill calls."""

from __future__ import annotations

import json

from temper_skills.export_tree import enrich_proposed, main, render_tests, tree_from_dict

TREE = {
    "fn_name": "can_dog_eat",
    "features": ["food_item", "food_form"],
    "default_outcome": "unknown",
    "model": "claude-sonnet-4-6 via claude-code-subagents",
    "profile": "standard",
    "nodes": [
        {"condition": 'food_item == "chocolate"', "outcome": "toxic",
         "rounds_survived": 12, "sources": ["domain_expert"]},
        {"condition": 'food_item == "peanut butter" and food_form == "low_fat"',
         "outcome": "xylitol risk", "sources": ["edge_case_hunter"], "gray_zone": "check label"},
    ],
}


def test_tree_from_dict_maps_fields():
    t = tree_from_dict(TREE)
    assert t.fn_name == "can_dog_eat"
    assert t.features == ["food_item", "food_form"]
    assert len(t.nodes) == 2
    assert t.nodes[0].rounds_survived == 12
    assert t.nodes[1].gray_zone == "check label"
    assert t.nodes[1].rounds_survived == 1  # default when absent


def test_main_writes_file_and_runs(tmp_path):
    src = tmp_path / "tree.json"
    src.write_text(json.dumps(TREE))
    out = tmp_path / "checker.py"
    assert main([str(src), str(out)]) == 0
    ns: dict = {}
    exec(compile(out.read_text(), "<gen>", "exec"), ns)
    assert ns["can_dog_eat"]({"food_item": "chocolate"}) == "toxic"
    assert ns["can_dog_eat"]({"food_item": "peanut butter", "food_form": "low_fat"}) == "xylitol risk"


def test_main_reads_stdin(tmp_path, monkeypatch, capsys):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(TREE)))
    out = tmp_path / "checker.py"
    assert main(["-", str(out)]) == 0
    assert out.exists()


def test_main_usage_error():
    assert main(["only-one-arg"]) == 2


def test_enrich_proposed_computes_prediction_and_status():
    t = tree_from_dict(TREE)
    raw = [{"input": {"food_item": "chocolate"}, "expected": "toxic", "rationale": "r"},
           {"input": {"food_item": "carrot"}, "expected": "toxic", "rationale": "contested"}]
    enriched = enrich_proposed(t, raw)
    assert all(e["status"] == "proposed" for e in enriched)          # never auto-ratified
    assert enriched[0]["tree_prediction"] == "toxic"                 # agrees with the tree
    assert enriched[1]["tree_prediction"] == "unknown"               # differs → worth a human


def test_main_writes_proposed_examples_sidecar(tmp_path):
    tree_with_proposed = {**TREE, "proposed_examples": [
        {"input": {"food_item": "macadamia"}, "expected": "toxic", "rationale": "nut gray zone"},
    ]}
    src = tmp_path / "tree.json"
    src.write_text(json.dumps(tree_with_proposed))
    out = tmp_path / "checker.py"
    assert main([str(src), str(out)]) == 0
    side = tmp_path / "checker.proposed_examples.json"
    assert side.exists()
    data = json.loads(side.read_text())
    assert data[0]["status"] == "proposed"
    assert data[0]["tree_prediction"] == "unknown"  # exporter computed it, not the LLM


def test_main_no_sidecar_without_proposed(tmp_path):
    src = tmp_path / "tree.json"
    src.write_text(json.dumps(TREE))
    out = tmp_path / "checker.py"
    main([str(src), str(out)])
    assert not (tmp_path / "checker.proposed_examples.json").exists()


def test_enrich_respects_explicit_status():
    t = tree_from_dict(TREE)
    raw = [{"input": {"food_item": "carrot"}, "expected": "unknown", "status": "resolved"}]
    assert enrich_proposed(t, raw)[0]["status"] == "resolved"  # passed-in status preserved


def test_main_emits_runnable_behavior_lock_test(tmp_path):
    tree_with = {**TREE, "proposed_examples": [
        {"input": {"food_item": "chocolate"}, "expected": "toxic", "rationale": "agrees"},
    ]}
    src = tmp_path / "tree.json"; src.write_text(json.dumps(tree_with))
    out = tmp_path / "checker.py"
    assert main([str(src), str(out)]) == 0
    test_file = tmp_path / "test_checker.py"
    assert test_file.exists()
    text = test_file.read_text()
    assert "from checker import can_dog_eat" in text and "def test_can_dog_eat_behavior" in text


def test_render_tests_locks_agreement_and_xfails_open_disputes():
    t = tree_from_dict(TREE)
    enriched = enrich_proposed(t, [
        {"input": {"food_item": "chocolate"}, "expected": "toxic"},        # agrees → LOCKED
        {"input": {"food_item": "carrot"}, "expected": "toxic"},           # proposed, differs → OPEN
        {"input": {"food_item": "carrot"}, "expected": "unknown", "status": "resolved"},  # resolved → LOCKED
    ])
    src = render_tests("checker", "can_dog_eat", enriched)
    assert "LOCKED = [" in src and "def test_can_dog_eat_behavior" in src
    # the only genuine dispute (proposed + label != tree) is xfailed, not silently locked
    assert "OPEN = [" in src and "xfail" in src
    assert "def test_can_dog_eat_open_disputes" in src
    # compiles to valid python
    compile(src, "<gen>", "exec")
