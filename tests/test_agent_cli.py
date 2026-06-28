"""AgentCliBackend: JSON scraping, the corrective retry, and CLI runnability probe."""

from __future__ import annotations

import pytest

from temper_skills.backends import agent_cli
from temper_skills.backends.agent_cli import AgentCliBackend, _extract_json, cli_runs
from temper_skills.schemas import PersonaVerdict


@pytest.mark.parametrize(
    "text,expected_key",
    [
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('preamble {"a": 1, "b": "x"} trailing', '{"a": 1, "b": "x"}'),
        ('{"outer": {"inner": 2}}', '{"outer": {"inner": 2}}'),
        ('{"s": "has } brace and { in string"}', '{"s": "has } brace and { in string"}'),
    ],
)
def test_extract_json_variants(text, expected_key):
    assert _extract_json(text) == expected_key


def test_extract_json_none_when_absent():
    assert _extract_json("no json here at all") is None


def test_complete_first_try(monkeypatch):
    be = AgentCliBackend(preset="opencode", model="m")
    monkeypatch.setattr(be, "_run",
                        lambda p: '{"persona":"literalist","score":8,"verdict":"ok","detail":"ok"}')
    v = be.complete("sys", "usr", PersonaVerdict)
    assert v.persona == "literalist" and v.score == 8


def test_complete_retries_then_succeeds(monkeypatch):
    be = AgentCliBackend(preset="opencode", model="m")
    calls = {"n": 0}

    def fake_run(prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            return "sorry, here is the answer in prose"  # no JSON -> retry
        return '{"persona":"edge_case_hunter","score":9,"verdict":"ok","detail":"solid"}'

    monkeypatch.setattr(be, "_run", fake_run)
    v = be.complete("sys", "usr", PersonaVerdict)
    assert calls["n"] == 2 and v.persona == "edge_case_hunter"


def test_complete_raises_after_two_failures(monkeypatch):
    be = AgentCliBackend(preset="opencode", model="m")
    monkeypatch.setattr(be, "_run", lambda p: "never any json")
    with pytest.raises(RuntimeError):
        be.complete("sys", "usr", PersonaVerdict)


def test_unknown_preset_rejected():
    with pytest.raises(ValueError):
        AgentCliBackend(preset="nope")


def test_cli_runs_true(monkeypatch):
    monkeypatch.setattr(agent_cli.shutil, "which", lambda b: "/usr/bin/" + b)

    class P:
        returncode = 0

    monkeypatch.setattr(agent_cli.subprocess, "run", lambda *a, **k: P())
    assert cli_runs("claude") is True


def test_cli_runs_false_when_missing(monkeypatch):
    monkeypatch.setattr(agent_cli.shutil, "which", lambda b: None)
    assert cli_runs("claude") is False


def test_cli_runs_false_when_crashing(monkeypatch):
    monkeypatch.setattr(agent_cli.shutil, "which", lambda b: "/usr/bin/" + b)

    def boom(*a, **k):
        raise OSError("crash")

    monkeypatch.setattr(agent_cli.subprocess, "run", boom)
    assert cli_runs("claude") is False
