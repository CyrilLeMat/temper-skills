"""End-to-end command flows (ingest --json, guide --json) on a fake backend — the
paths an agent drives; stdout must be a parseable manifest, artifacts must exist."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from temper_skills import cli
from temper_skills.audit import JudgeScores

from conftest import FakeBackend

runner = CliRunner()


class AuditableBackend(FakeBackend):
    """FakeBackend + audit judging, so `guide` can run audit → temper end to end.
    The inferred schema pins `priority` to a closed set — otherwise the audit routes
    the open feature to build_normalizer instead of temper."""

    def complete(self, system, user, schema):
        from temper_skills.ingest import InferredFeature, InferredSchema

        if schema is JudgeScores:
            return JudgeScores(decisiveness=9, combinatorics=8, stakes=8)
        if schema is InferredSchema:
            return InferredSchema(
                fn_name="route_ticket",
                features=[
                    InferredFeature(
                        name="priority", type="string", description='one of "low", "high"'
                    ),
                    InferredFeature(name="security_score", type="number"),
                ],
            )
        return super().complete(system, user, schema)


def _skill(tmp_path) -> Path:
    p = tmp_path / "skill.md"
    p.write_text("# route tickets by priority and security score")
    return p


def test_ingest_json_emits_manifest_and_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_backend", lambda n, m: AuditableBackend())
    out = tmp_path / "out" / "route.py"
    res = runner.invoke(
        cli.app,
        ["ingest", str(_skill(tmp_path)), "--json", "--profile", "quick", "--out", str(out)],
    )
    assert res.exit_code == 0, res.output
    m = json.loads(res.stdout)  # panels went to stderr; stdout is pure manifest
    assert m["fn_name"] == "route_ticket"
    assert Path(m["tree_path"]).exists()
    assert Path(m["tempered_skill_path"]).exists()
    assert m["validation_case_count"] > 0
    assert m["backend"] and "cost_usd" in m


def test_guide_json_compiles_on_a_temper_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_backend", lambda n, m: AuditableBackend())
    out_dir = tmp_path / "out"
    res = runner.invoke(
        cli.app, ["guide", str(_skill(tmp_path)), "--json", "--out-dir", str(out_dir)]
    )
    assert res.exit_code == 0, res.output
    m = json.loads(res.stdout)
    assert m["status"] == "compiled"
    assert m["action_taken"] == "temper"
    assert m["audit"]["verdict"] == "temper"
    assert Path(m["final_skill_path"]).exists()
    assert any(a.endswith("route_ticket.py") for a in m["artifacts"])


def test_guide_json_relays_non_auto_actions(tmp_path, monkeypatch):
    class ProseBackend(AuditableBackend):
        def complete(self, system, user, schema):
            if schema is JudgeScores:
                return JudgeScores(decisiveness=2, combinatorics=2, stakes=3)
            return super().complete(system, user, schema)

    monkeypatch.setattr(cli, "get_backend", lambda n, m: ProseBackend())
    res = runner.invoke(
        cli.app, ["guide", str(_skill(tmp_path)), "--json", "--out-dir", str(tmp_path / "o")]
    )
    assert res.exit_code == 0
    m = json.loads(res.stdout)
    assert m["status"] == "action_not_auto_run"
    assert m["final_skill_path"] is None


def test_ingest_propose_schema_stops_and_emits_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_backend", lambda n, m: AuditableBackend())
    monkeypatch.chdir(tmp_path)  # schema.proposed.py is written to the cwd
    res = runner.invoke(cli.app, ["ingest", str(_skill(tmp_path)), "--propose-schema", "--json"])
    assert res.exit_code == 0
    m = json.loads(res.stdout)
    assert Path(m["proposed_schema_path"]).exists()
    assert {f["name"] for f in m["features"]} == {"priority", "security_score"}
    assert not list(tmp_path.glob("*.generated.py"))  # it stopped — no distill ran


def test_ingest_require_fit_exits_3_on_skip(tmp_path, monkeypatch):
    class SkipBackend(AuditableBackend):
        def complete(self, system, user, schema):
            if schema is JudgeScores:
                return JudgeScores(decisiveness=2, combinatorics=2, stakes=2)
            return super().complete(system, user, schema)

    monkeypatch.setattr(cli, "get_backend", lambda n, m: SkipBackend())
    res = runner.invoke(
        cli.app,
        [
            "ingest",
            str(_skill(tmp_path)),
            "--require-fit",
            "--json",
            "--out",
            str(tmp_path / "t.py"),
        ],
    )
    assert res.exit_code == 3
