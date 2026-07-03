"""`temper-skills audit <dir>` — the library sweep — and the bare-invocation shim."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from temper_skills import cli
from temper_skills.audit import JudgeScores
from temper_skills.backends.base import Backend
from temper_skills.ingest import InferredFeature, InferredSchema

runner = CliRunner()
# No console fixture needed: each command builds its own Console, so there is no
# module-global to reset between tests.


class RoutingBackend(Backend):
    """Scores by marker in the skill text, so one fake serves a whole library:
    TEMPERME → clean temper; SKIPME → generation skill (skip)."""

    name = "fake"

    def __init__(self):
        super().__init__("fake-model")

    def complete(self, system, user, schema):
        skip = "SKIPME" in user
        if schema is InferredSchema:
            if skip:
                return InferredSchema(
                    fn_name="write_post",
                    features=[
                        InferredFeature(name="topic", type="string", description="the topic")
                    ],
                )
            return InferredSchema(
                fn_name="route_ticket",
                features=[
                    InferredFeature(
                        name="priority", type="string", description='one of "low", "high"'
                    ),
                    InferredFeature(name="security_score", type="number"),
                ],
            )
        if schema is JudgeScores:
            if skip:
                return JudgeScores(decisiveness=2, combinatorics=3, stakes=3)
            return JudgeScores(decisiveness=9, combinatorics=8, stakes=8)
        raise AssertionError(f"unexpected schema {schema}")


def _lib(tmp_path):
    lib = tmp_path / "lib"
    (lib / "router").mkdir(parents=True)
    (lib / "router" / "SKILL.md").write_text("# TEMPERME route tickets")
    (lib / "writer").mkdir()
    (lib / "writer" / "SKILL.md").write_text("# SKIPME write a blog post")
    return lib


def test_dir_sweep_ranks_actionable_first_and_exits_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_backend", lambda n, m: RoutingBackend())
    res = runner.invoke(cli.app, ["audit", str(_lib(tmp_path))])
    assert res.exit_code == 0
    assert "FREEZE-WORTHY" in res.output
    assert "NOTHING TO" in res.output
    assert res.output.index("router") < res.output.index("writer")  # ranked


def test_dir_sweep_all_skips_exits_3(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    (lib / "w").mkdir(parents=True)
    (lib / "w" / "SKILL.md").write_text("# SKIPME prose")
    monkeypatch.setattr(cli, "get_backend", lambda n, m: RoutingBackend())
    res = runner.invoke(cli.app, ["audit", str(lib)])
    assert res.exit_code == 3


def test_dir_sweep_empty_dir_exits_2(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_backend", lambda n, m: RoutingBackend())
    res = runner.invoke(cli.app, ["audit", str(tmp_path)])
    assert res.exit_code == 2


def test_dir_sweep_json_is_a_report_list(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_backend", lambda n, m: RoutingBackend())
    res = runner.invoke(cli.app, ["audit", str(_lib(tmp_path)), "--json"])
    assert res.exit_code == 0
    rows = json.loads(res.output)
    assert len(rows) == 2
    assert rows[0]["verdict"] == "temper" and rows[0]["path"].endswith("router/SKILL.md")
    assert rows[1]["verdict"] == "skip"


def test_dir_sweep_json_with_report_keeps_stdout_parseable(tmp_path, monkeypatch):
    # Regression: the "report → …" console line must go to stderr, never corrupt
    # the JSON stream on stdout (bit the first live corpus sweep).
    monkeypatch.setattr(cli, "get_backend", lambda n, m: RoutingBackend())
    out = tmp_path / "audit.md"
    res = runner.invoke(cli.app, ["audit", str(_lib(tmp_path)), "--json", "--report", str(out)])
    assert res.exit_code == 0
    assert len(json.loads(res.stdout)) == 2
    assert out.exists()


def test_dir_sweep_writes_md_report(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_backend", lambda n, m: RoutingBackend())
    out = tmp_path / "audit.md"
    res = runner.invoke(cli.app, ["audit", str(_lib(tmp_path)), "--report", str(out)])
    assert res.exit_code == 0
    md = out.read_text()
    assert "| skill | verdict |" in md and "FREEZE-WORTHY" in md


def test_single_skill_report_md(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_backend", lambda n, m: RoutingBackend())
    skill = tmp_path / "skill.md"
    skill.write_text("# TEMPERME route tickets")
    out = tmp_path / "audit.md"
    res = runner.invoke(cli.app, ["audit", str(skill), "--report", str(out), "--json"])
    assert res.exit_code == 0
    assert "# Skill audit" in out.read_text()


# ---- bare invocation: `temper-skills <path>` ----


def test_implicit_command_dir_audits(tmp_path):
    assert cli._implicit_command(str(tmp_path)) == "audit"


def test_implicit_command_file_guides(tmp_path):
    p = tmp_path / "skill.md"
    p.write_text("# s")
    assert cli._implicit_command(str(p)) == "guide"


def test_implicit_command_never_shadows_a_subcommand(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "audit").mkdir()  # a dir named like a command: the command wins
    assert cli._implicit_command("audit") is None


def test_implicit_command_ignores_flags_and_missing_paths():
    assert cli._implicit_command("--help") is None
    assert cli._implicit_command("no/such/path.md") is None
