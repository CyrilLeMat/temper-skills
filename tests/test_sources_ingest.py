"""Sources normalization, default personas, and ingest_skill schema inference."""

from __future__ import annotations

import pytest
from conftest import FakeBackend, TicketSchema

from temper_skills import DEFAULT_PERSONAS, OVERENGINEERING_CRITIC, Sources
from temper_skills.ingest import ingest_skill


def test_sources_from_pydantic_model():
    s = Sources(schema=TicketSchema)
    assert s.feature_names == ["priority", "security_score"]
    assert s.json_schema["type"] == "object"


def test_sources_from_json_schema_dict():
    s = Sources(schema={"type": "object", "properties": {"a": {"type": "string"}}})
    assert s.feature_names == ["a"]


def test_sources_rejects_bad_schema():
    with pytest.raises(TypeError):
        Sources(schema=42)


def test_default_personas_exclude_overengineering_critic():
    # the critic is appended by distill, not part of the default attacker list
    assert OVERENGINEERING_CRITIC not in DEFAULT_PERSONAS
    assert len(DEFAULT_PERSONAS) == 4


def test_ingest_infers_schema_and_runs(tmp_path):
    skill = tmp_path / "skill.md"
    skill.write_text("Route tickets. When in doubt, human_review.")
    be = FakeBackend(score=9)
    tree = ingest_skill(str(skill), schema=None, backend=be, profile="quick")
    assert be.calls["inferred"] == 1            # schema inference happened once
    assert tree.fn_name == "route_ticket"        # taken from the inferred schema
    assert "priority" in tree.features


def test_ingest_confirm_veto_aborts(tmp_path):
    skill = tmp_path / "skill.md"
    skill.write_text("anything")
    be = FakeBackend(score=9)
    with pytest.raises(KeyboardInterrupt):
        ingest_skill(str(skill), schema=None, backend=be, confirm=lambda inferred: False)


def test_ingest_explicit_schema_skips_inference(tmp_path):
    skill = tmp_path / "skill.md"
    skill.write_text("Route tickets.")
    be = FakeBackend(score=9)
    tree = ingest_skill(str(skill), schema=TicketSchema, backend=be, profile="quick",
                        fn_name="route")
    assert be.calls["inferred"] == 0
    assert tree.fn_name == "route"


def test_ingest_threads_examples_to_the_check(tmp_path):
    skill = tmp_path / "skill.md"
    skill.write_text("Route tickets.")
    be = FakeBackend(score=9)
    tree = ingest_skill(
        str(skill), schema=TicketSchema, backend=be, profile="quick",
        examples=[{"input": {"priority": "high", "security_score": 0.1},
                   "expected": "escalate_urgent"}],
    )
    assert tree.example_report is not None
    assert tree.example_report.total == 1 and tree.example_report.disagreements == []
