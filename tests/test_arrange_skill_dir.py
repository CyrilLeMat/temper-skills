"""arrange_skill_dir emits a spec-compliant Agent Skill folder (agentskills.io layout)."""

from __future__ import annotations

import json

from temper_skills.export_skill import arrange_skill_dir
from temper_skills.export_tree import tree_from_dict
from temper_skills.skill_render import main as skill_render_main


def _tree(fn, feat, cond, out):
    t = tree_from_dict({
        "fn_name": fn, "features": [feat], "default_outcome": "unknown",
        "nodes": [{"condition": cond, "outcome": out}],
    })
    t.proposed_examples = [
        {"input": {feat: "hit"}, "expected": out, "rationale": "match", "status": "proposed"},
        {"input": {feat: "miss"}, "expected": out, "rationale": "contested", "status": "proposed"},
    ]
    return t


def test_layout_matches_spec(tmp_path):
    d = tmp_path / "dog-day"
    arrange_skill_dir(
        str(d), "dog-day",
        [
            {"tree": _tree("decide_a", "x", "(x or '')=='hit'", "yes"),
             "module": "decide_a", "schema_src": "class A: ...\n"},
            {"tree": _tree("decide_b", "y", "(y or '')=='hit'", "go"),
             "module": "decide_b", "schema_src": "class B: ...\n", "consumes": ["decide_a"]},
        ],
        generative_steps=["write a note"],
        original_skill_text="You are a helper.",
    )
    # SKILL.md + the two spec subdirs
    assert (d / "SKILL.md").exists()
    assert (d / "scripts").is_dir() and (d / "assets").is_dir()
    # trees + tests in scripts/
    for m in ("decide_a", "decide_b"):
        assert (d / "scripts" / f"{m}.py").exists()
        assert (d / "scripts" / f"test_{m}.py").exists()
    # schemas + validation datasets in assets/ (spec: "Data files … schemas")
    for m in ("decide_a", "decide_b"):
        assert (d / "assets" / f"{m}.schema.py").exists()
        assert (d / "assets" / f"{m}.validation.jsonl").exists()


def test_trees_are_self_contained(tmp_path):
    d = tmp_path / "s"
    arrange_skill_dir(str(d), "s", [{"tree": _tree("decide_a", "x", "(x or '')=='hit'", "yes"),
                                     "module": "decide_a"}])
    src = (d / "scripts" / "decide_a.py").read_text()
    assert "import " not in src  # zero-dependency; nothing to install


def test_skill_md_frontmatter_and_scripts_imports(tmp_path):
    d = tmp_path / "dog-day"
    arrange_skill_dir(str(d), "dog-day",
                      [{"tree": _tree("decide_a", "x", "(x or '')=='hit'", "yes"),
                        "module": "decide_a"}])
    md = (d / "SKILL.md").read_text()
    assert md.startswith("---")
    assert "name: dog-day" in md          # name matches the directory
    assert "from scripts.decide_a import decide_a" in md   # scripts/ layout imports


def test_cli_main_arranges_from_spec(tmp_path):
    """The subagent-mode entrypoint: spec.json (+ per-decision tree.json) -> full skill dir."""
    (tmp_path / "walk.json").write_text(json.dumps({
        "fn_name": "decide_walk", "features": ["weather"], "default_outcome": "normal_walk",
        "nodes": [{"condition": "(weather or '').strip().lower()=='storm'", "outcome": "skip"}],
        "proposed_examples": [{"input": {"weather": "storm"}, "expected": "skip"}],
    }))
    (tmp_path / "walk.schema.py").write_text("class W: ...\n")
    (tmp_path / "spec.json").write_text(json.dumps({
        "name": "route", "description": "d",
        "decisions": [{"tree": "walk.json", "module": "decide_walk", "schema": "walk.schema.py"}],
    }))
    rc = skill_render_main([str(tmp_path / "spec.json"), str(tmp_path / "route")])
    assert rc == 0
    d = tmp_path / "route"
    assert (d / "SKILL.md").exists()
    assert (d / "scripts" / "decide_walk.py").exists()
    assert (d / "assets" / "decide_walk.schema.py").exists()
    assert (d / "assets" / "decide_walk.validation.jsonl").exists()
    assert "name: route" in (d / "SKILL.md").read_text()


def test_behavior_lock_is_green(tmp_path):
    d = tmp_path / "s"
    arrange_skill_dir(str(d), "s", [{"tree": _tree("decide_a", "x", "(x or '')=='hit'", "yes"),
                                     "module": "decide_a"}])
    ns: dict = {}
    exec(compile((d / "scripts" / "decide_a.py").read_text(), "<g>", "exec"), ns)
    rows = [json.loads(l) for l in (d / "assets" / "decide_a.validation.jsonl")
            .read_text().splitlines() if l.strip()]
    for r in rows:
        assert ns["decide_a"](r["input"]) == r["tree_prediction"]   # locked to the tree's own output
