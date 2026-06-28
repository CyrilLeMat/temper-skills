"""The deterministic JSON -> .py exporter the skill calls."""

from __future__ import annotations

import json

from temper_skills.export_tree import main, tree_from_dict

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
