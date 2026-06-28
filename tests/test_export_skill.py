"""The tempered skill.md: delegates the decision to the tree (close the loop)."""

from __future__ import annotations

from temper_skills.export_skill import main, render_tempered_skill
from temper_skills.tree import DecisionNode, DecisionTree


def _tree():
    return DecisionTree(
        nodes=[
            DecisionNode('food_item == "chocolate"', "no — toxic"),
            DecisionNode('food_item == "carrot"', "yes", gray_zone="no ratified safe examples"),
        ],
        default_outcome="no — when in doubt",
        features=["food_item", "dog_weight_kg"],
        fn_name="can_dog_eat",
        model="claude-x",
    )


def test_delegates_to_the_tree():
    md = render_tempered_skill(_tree(), "dog_food_checker",
                               original_skill_text="You are a dog food safety assistant.")
    assert "decision is frozen" in md.lower()
    assert "from dog_food_checker import can_dog_eat" in md
    # both features listed for extraction
    assert "`food_item`" in md and "`dog_weight_kg`" in md
    # role carried from the original skill
    assert "You are a dog food safety assistant." in md


def test_gray_zones_surfaced():
    md = render_tempered_skill(_tree(), "m")
    assert "Gray zones to surface" in md
    assert "no ratified safe examples" in md


def test_generic_role_when_no_original():
    md = render_tempered_skill(_tree(), "m")
    assert "You are an assistant." in md


def test_no_gray_zone_section_when_none():
    t = DecisionTree(nodes=[DecisionNode('x == 1', "a")], default_outcome="b",
                     features=["x"], fn_name="decide")
    md = render_tempered_skill(t, "m")
    assert "Gray zones" not in md


def test_main_writes_file(tmp_path):
    import json
    tj = tmp_path / "tree.json"
    tj.write_text(json.dumps({
        "fn_name": "can_dog_eat", "features": ["food_item"],
        "default_outcome": "no", "nodes": [{"condition": 'food_item == "x"', "outcome": "no"}],
    }))
    out = tmp_path / "skill.tempered.md"
    assert main([str(tj), "dog_food_checker", str(out)]) == 0
    text = out.read_text()
    assert "from dog_food_checker import can_dog_eat" in text
