"""The tempered skill.md: delegates the decision to the tree (close the loop)."""

from __future__ import annotations

from conftest import FakeBackend

from temper_skills.export_skill import main, render_tempered_skill, weave_tempered_skill
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
    md = render_tempered_skill(
        _tree(), "dog_food_checker", original_skill_text="You are a dog food safety assistant."
    )
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
    t = DecisionTree(
        nodes=[DecisionNode("x == 1", "a")], default_outcome="b", features=["x"], fn_name="decide"
    )
    md = render_tempered_skill(t, "m")
    assert "Gray zones" not in md


def test_woven_uses_the_backend():
    be = FakeBackend()
    md = weave_tempered_skill(
        _tree(), "dog_food_checker", "You are a dog food safety assistant.", be
    )
    assert be.calls["woven"] == 1
    assert "Woven skill" in md  # FakeBackend's canned markdown


def test_main_writes_file(tmp_path):
    import json

    tj = tmp_path / "tree.json"
    tj.write_text(
        json.dumps(
            {
                "fn_name": "can_dog_eat",
                "features": ["food_item"],
                "default_outcome": "no",
                "nodes": [{"condition": 'food_item == "x"', "outcome": "no"}],
            }
        )
    )
    out = tmp_path / "skill.tempered.md"
    assert main([str(tj), "dog_food_checker", str(out)]) == 0
    text = out.read_text()
    assert "from dog_food_checker import can_dog_eat" in text


def _parse_frontmatter(md: str) -> dict:
    assert md.startswith("---\n"), "must open with a YAML frontmatter block"
    _, fm, _ = md.split("---\n", 2)
    out = {}
    for line in fm.strip().splitlines():
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip()
    return out


def test_frontmatter_present_and_valid():
    md = render_tempered_skill(_tree(), "dog_food_checker")
    fm = _parse_frontmatter(md)
    # required fields present, name spec-valid (lowercase, hyphens, no underscores)
    assert fm["name"] == "dog-food-checker"
    assert fm["description"].startswith('"') and len(fm["description"]) <= 1024
    assert "_" not in fm["name"] and fm["name"] == fm["name"].lower()


def test_dir_mode_emits_spec_compliant_skill(tmp_path):
    import json

    tj = tmp_path / "tree.json"
    tj.write_text(
        json.dumps(
            {
                "fn_name": "decide_walk",
                "features": ["weather"],
                "default_outcome": "normal_walk",
                "nodes": [
                    {
                        "condition": '(weather or "").lower() == "storm"',
                        "outcome": "toilet_break_only",
                    }
                ],
            }
        )
    )
    # underscore in the requested dir name must be sanitized to a hyphenated skill name
    assert main([str(tj), "decide_walk", str(tmp_path / "dog_day")]) == 0
    skill_dir = tmp_path / "dog-day"
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "scripts" / "decide_walk.py").exists()
    text = (skill_dir / "SKILL.md").read_text()
    fm = _parse_frontmatter(text)
    assert fm["name"] == "dog-day" == skill_dir.name  # name matches parent dir (spec rule)
    assert "scripts/decide_walk.py" in text
