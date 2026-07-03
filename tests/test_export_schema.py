"""render_schema_source / normalization_notes and the --propose-schema round-trip."""

from __future__ import annotations

from conftest import FakeBackend

from temper_skills.pipelines import load_schema as _load_schema
from temper_skills.export_schema import (
    _classname,
    normalization_notes,
    render_schema_source,
)
from temper_skills.ingest import InferredFeature, InferredSchema, ingest_skill


def _inferred(features, fn_name="route_ticket", constraints=None):
    return InferredSchema(
        fn_name=fn_name,
        features=[InferredFeature(**f) for f in features],
        constraints=constraints or [],
    )


def test_classname_pascalcases():
    assert _classname("route_ticket") == "RouteTicket"
    assert _classname("can_dog_eat") == "CanDogEat"


def test_rendered_source_is_loadable_pydantic(tmp_path):
    src = render_schema_source(
        _inferred(
            [{"name": "priority", "type": "string"}, {"name": "security_score", "type": "number"}]
        )
    )
    p = tmp_path / "schema.proposed.py"
    p.write_text(src)
    cls = _load_schema(f"{p}:RouteTicket")
    assert set(cls.model_json_schema()["properties"]) == {"priority", "security_score"}


def test_empty_schema_renders_pass(tmp_path):
    p = tmp_path / "s.py"
    p.write_text(render_schema_source(_inferred([])))
    cls = _load_schema(f"{p}:RouteTicket")
    assert cls.model_json_schema()["properties"] == {}


def test_normalization_notes_flag_exact_match_and_enum():
    notes = normalization_notes(
        _inferred(
            [
                {"name": "food_item", "type": "string", "description": "the food the dog ate"},
                {
                    "name": "food_form",
                    "type": "string",
                    "description": 'one of "standard", "raw", "cooked"',
                },
                {"name": "weight", "type": "number"},
            ]
        )
    )
    assert "exact-match" in notes["food_item"]
    assert "Literal" in notes["food_form"]
    assert "weight" not in notes  # numeric fields carry no normalizer burden


def test_constraints_rendered_as_comments():
    src = render_schema_source(
        _inferred([{"name": "x", "type": "boolean"}], constraints=["when in doubt, human_review"])
    )
    assert "when in doubt, human_review" in src


def test_ingest_propose_schema_only_returns_without_distilling(tmp_path):
    skill = tmp_path / "skill.md"
    skill.write_text("Route tickets. When in doubt, human_review.")
    be = FakeBackend(score=9)
    out = ingest_skill(str(skill), schema=None, backend=be, propose_schema_only=True)
    assert isinstance(out, InferredSchema)
    assert be.calls["inferred"] == 1
    assert be.calls["tree"] == 0  # the loop never ran


def test_yes_flag_auto_accepts_inferred_schema(tmp_path, monkeypatch):
    """`-y` runs the full ingest without the schema y/n prompt firing."""
    from unittest.mock import patch
    from typer.testing import CliRunner
    from rich.prompt import Prompt
    from temper_skills import cli

    skill = tmp_path / "skill.md"
    skill.write_text("Route tickets. When in doubt, human_review.")
    monkeypatch.chdir(tmp_path)

    def _boom(*a, **k):
        raise AssertionError("Prompt.ask must not fire under -y")

    with (
        patch.object(cli, "get_backend", lambda *a, **k: FakeBackend(score=9)),
        patch.object(Prompt, "ask", _boom),
    ):
        r = CliRunner().invoke(cli.app, ["ingest", str(skill), "--profile", "quick", "-y"])
    assert r.exit_code == 0, r.output
    assert "auto-accepted" in r.output
