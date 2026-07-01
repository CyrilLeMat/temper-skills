"""The deterministic JSON -> .py exporter the skill calls."""

from __future__ import annotations

import json

from temper_skills.export_tree import (
    enrich_validation,
    main,
    render_behavior_lock,
    render_ratified,
    tree_from_dict,
)

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


def test_enrich_validation_computes_prediction_agreement_and_status():
    t = tree_from_dict(TREE)
    raw = [
        {"input": {"food_item": "chocolate"}, "expected": "toxic", "rationale": "r"},
        {"input": {"food_item": "carrot"}, "expected": "toxic", "rationale": "contested"},
        {"input": {"food_item": "carrot"}, "rationale": "no label to compare"},
    ]
    enriched = enrich_validation(t, raw)
    assert all(e["status"] == "proposed" for e in enriched)          # never auto-ratified
    assert enriched[0]["tree_prediction"] == "toxic" and enriched[0]["agrees"] is True
    assert enriched[1]["tree_prediction"] == "unknown" and enriched[1]["agrees"] is False
    assert enriched[2]["agrees"] is None                             # no expected → nothing to compare


def test_enrich_respects_explicit_status_and_passes_through_provenance():
    t = tree_from_dict(TREE)
    raw = [{"input": {"food_item": "carrot"}, "expected": "unknown", "status": "resolved",
            "source": "domain_expert#r2", "round": 2}]
    e = enrich_validation(t, raw)[0]
    assert e["status"] == "resolved"          # passed-in status preserved
    assert e["source"] == "domain_expert#r2" and e["round"] == 2


def test_main_writes_validation_dataset(tmp_path):
    tree_with = {**TREE, "proposed_examples": [
        {"input": {"food_item": "macadamia"}, "expected": "toxic", "rationale": "nut gray zone"},
    ]}
    src = tmp_path / "tree.json"
    src.write_text(json.dumps(tree_with))
    out = tmp_path / "checker.py"
    assert main([str(src), str(out)]) == 0
    side = tmp_path / "checker.validation.jsonl"
    assert side.exists()
    rows = [json.loads(ln) for ln in side.read_text().splitlines() if ln.strip()]
    assert rows[0]["status"] == "proposed"
    assert rows[0]["tree_prediction"] == "unknown"   # exporter computed it, not the LLM
    assert rows[0]["agrees"] is False                # "toxic" proposed, tree says "unknown"
    # the old gitignored sidecar name is no longer produced by this path
    assert not (tmp_path / "checker.proposed_examples.json").exists()


def test_main_no_dataset_without_proposed(tmp_path):
    src = tmp_path / "tree.json"
    src.write_text(json.dumps(TREE))
    out = tmp_path / "checker.py"
    main([str(src), str(out)])
    assert not (tmp_path / "checker.validation.jsonl").exists()


def test_behavior_lock_is_always_green_and_has_no_xfail(tmp_path):
    """A proposed label the tree does NOT return must never become a failing/xfail test."""
    t = tree_from_dict(TREE)
    enriched = enrich_validation(t, [
        {"input": {"food_item": "chocolate"}, "expected": "toxic"},   # agrees
        {"input": {"food_item": "carrot"}, "expected": "toxic"},      # disagrees (tree: unknown)
    ])
    src = render_behavior_lock("checker", "can_dog_eat", enriched)
    assert "xfail" not in src and "OPEN" not in src
    assert "def test_can_dog_eat_behavior" in src
    assert "def test_can_dog_eat_open_disputes" not in src
    # the disagreeing case is locked to the TREE's answer, not the proposed label
    assert "'unknown'" in src
    compile(src, "<gen>", "exec")
    # invariant: every LOCKED row asserts exactly what the tree returns → always green
    ns: dict = {}
    exec(compile(t.to_source(), "<gen>", "exec"), ns)
    for c in enriched:
        assert ns["can_dog_eat"](c["input"]) == c["tree_prediction"]


def test_ratified_file_only_when_ratified_present(tmp_path):
    t = tree_from_dict(TREE)
    # nothing ratified → no ratified renderer output
    proposed_only = enrich_validation(t, [{"input": {"food_item": "carrot"}, "expected": "toxic"}])
    assert render_ratified("checker", "can_dog_eat", proposed_only) is None

    # a ratified case → a real assertion of the human label (can fail on regression)
    ratified = enrich_validation(t, [
        {"input": {"food_item": "chocolate"}, "expected": "toxic", "status": "ratified"},
    ])
    src = render_ratified("checker", "can_dog_eat", ratified)
    assert src is not None
    assert "def test_can_dog_eat_ratified" in src and "RATIFIED = [" in src
    assert "xfail" not in src
    compile(src, "<gen>", "exec")


def test_main_emits_behavior_lock_and_ratified_files(tmp_path):
    tree_with = {**TREE, "proposed_examples": [
        {"input": {"food_item": "chocolate"}, "expected": "toxic", "rationale": "agrees"},
        {"input": {"food_item": "peanut butter", "food_form": "low_fat"},
         "expected": "xylitol risk", "status": "ratified", "rationale": "human blessed"},
    ]}
    src = tmp_path / "tree.json"; src.write_text(json.dumps(tree_with))
    out = tmp_path / "checker.py"
    assert main([str(src), str(out)]) == 0
    lock = tmp_path / "test_checker.py"
    rat = tmp_path / "test_checker_ratified.py"
    assert lock.exists() and rat.exists()
    assert "def test_can_dog_eat_behavior" in lock.read_text()
    assert "def test_can_dog_eat_ratified" in rat.read_text()
