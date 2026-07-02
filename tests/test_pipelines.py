"""compile_tree — the one orchestration path behind ingest, guide/audit's temper, and
decompose --temper-each. Previously this sequence lived three times in cli.py, untested."""

from __future__ import annotations

import json

import pytest

from temper_skills.pipelines import compile_tree, load_schema, write_validation_artifacts

from conftest import FakeBackend


@pytest.fixture()
def skill(tmp_path):
    p = tmp_path / "skill.md"
    p.write_text("# route tickets by priority and security score")
    return p


def test_compile_tree_emits_tree_suite_and_tempered_skill(tmp_path, skill):
    be = FakeBackend()
    res = compile_tree(str(skill), be, out_dir=str(tmp_path / "out"), profile="quick")

    assert res.tree.fn_name == "route_ticket"
    assert res.tree_path.endswith("route_ticket.py")  # stem defaults to the fn_name
    assert "def route_ticket" in open(res.tree_path).read()

    assert res.suite is not None
    assert res.suite.cases == len(res.suite.enriched) > 0
    assert open(res.suite.dataset_path).read().strip()          # jsonl written
    assert "def test_route_ticket_behavior" in open(res.suite.test_path).read()

    assert res.skill_path.endswith("route_ticket.tempered.md")
    assert "route_ticket" in open(res.skill_path).read()
    assert res.weave_error is None


def test_compile_tree_stem_overrides_filenames(tmp_path, skill):
    res = compile_tree(str(skill), FakeBackend(), out_dir=str(tmp_path), stem="custom",
                       profile="quick")
    assert res.tree_path.endswith("custom.py")
    assert res.skill_path.endswith("custom.tempered.md")
    assert res.suite.test_path.endswith("test_custom.py")


def test_compile_tree_skill_style_none_skips_the_tempered_skill(tmp_path, skill):
    res = compile_tree(str(skill), FakeBackend(), out_dir=str(tmp_path),
                       profile="quick", skill_style=None)
    assert res.skill_path is None
    assert not list(tmp_path.glob("*.tempered.md"))


def test_compile_tree_woven_success(tmp_path, skill):
    be = FakeBackend()
    res = compile_tree(str(skill), be, out_dir=str(tmp_path), profile="quick",
                       skill_style="woven")
    assert res.weave_error is None
    assert be.calls["woven"] == 1
    assert "Woven skill" in open(res.skill_path).read()


def test_compile_tree_woven_failure_falls_back_to_template(tmp_path, skill):
    class WeaveCrash(FakeBackend):
        def complete(self, system, user, schema):
            from temper_skills.export_skill import WovenSkill
            if schema is WovenSkill:
                raise RuntimeError("model refused")
            return super().complete(system, user, schema)

    res = compile_tree(str(skill), WeaveCrash(), out_dir=str(tmp_path), profile="quick",
                       skill_style="woven")
    assert "model refused" in res.weave_error
    assert res.skill_path and "route_ticket" in open(res.skill_path).read()  # template fallback


def test_compile_tree_checkpoint_and_gate_are_honored(tmp_path, skill):
    seen = {"checkpoints": 0, "rounds": 0}

    def checkpoint(t):
        seen["checkpoints"] += 1

    def gate(r):
        seen["rounds"] += 1
        return "continue"

    compile_tree(str(skill), FakeBackend(), out_dir=str(tmp_path), profile="quick",
                 gate=gate, checkpoint=checkpoint)
    assert seen["rounds"] > 0
    assert seen["checkpoints"] > 0


def test_write_validation_artifacts_none_without_proposals(tmp_path, skill):
    res = compile_tree(str(skill), FakeBackend(), out_dir=str(tmp_path), profile="quick",
                       propose_examples=False)
    assert res.suite is None
    # and calling the writer directly on such a tree is a clean no-op
    assert write_validation_artifacts(res.tree, res.tree_path) is None


def test_load_schema_rejects_bad_spec(tmp_path):
    with pytest.raises(ValueError):
        load_schema(str(tmp_path / "not_a_schema.py"))  # no ':ClassName'


def test_load_schema_json(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"properties": {"x": {"type": "string"}}}))
    assert load_schema(str(p))["properties"]["x"] == {"type": "string"}
