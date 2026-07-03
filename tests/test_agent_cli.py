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
    monkeypatch.setattr(
        be, "_run", lambda p: '{"persona":"literalist","score":8,"verdict":"ok","detail":"ok"}'
    )
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


def test_preset_argv_and_text_extractors():
    from temper_skills.backends.agent_cli import (
        _claude_argv,
        _claude_text,
        _opencode_argv,
        _opencode_text,
        _qualify_opencode_model,
    )

    assert _claude_argv("hi", "claude-sonnet-4-6") == [
        "claude",
        "-p",
        "hi",
        "--model",
        "claude-sonnet-4-6",
        "--output-format",
        "json",
    ]
    assert _claude_text('{"result": "the reply"}') == "the reply"
    assert _opencode_argv("hi", "claude-sonnet-4-6")[-1] == "anthropic/claude-sonnet-4-6"
    assert _qualify_opencode_model("openai/gpt-4o") == "openai/gpt-4o"
    assert _opencode_text("raw stdout") == "raw stdout"


def test_extract_json_handles_escaped_quotes_and_unbalanced():
    assert _extract_json('{"s": "escaped \\" quote"}') == '{"s": "escaped \\" quote"}'
    assert _extract_json('{"never": "closes"') is None


def test_run_returns_extracted_text(monkeypatch):
    be = AgentCliBackend(preset="claude", model="m")

    class P:
        returncode = 0
        stdout = '{"result": "hello"}'
        stderr = ""

    monkeypatch.setattr(agent_cli.subprocess, "run", lambda *a, **k: P())
    assert be._run("prompt") == "hello"


def test_run_raises_on_nonzero_exit(monkeypatch):
    be = AgentCliBackend(preset="opencode", model="m")

    class P:
        returncode = 3
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(agent_cli.subprocess, "run", lambda *a, **k: P())
    with pytest.raises(RuntimeError, match="exited 3"):
        be._run("prompt")


def test_complete_retries_on_schema_invalid_json(monkeypatch):
    be = AgentCliBackend(preset="opencode", model="m")
    calls = {"n": 0}

    def fake_run(prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            return '{"wrong_field": true}'  # JSON but not the schema -> ValidationError retry
        return '{"persona":"literalist","score":7,"verdict":"ok","detail":"d"}'

    monkeypatch.setattr(be, "_run", fake_run)
    v = be.complete("sys", "usr", PersonaVerdict)
    assert calls["n"] == 2 and v.score == 7


# ---- transient CLI failures join the retry path (a timeout must not bypass it) ----


def test_complete_retries_after_timeout_then_succeeds(monkeypatch):
    import subprocess

    be = AgentCliBackend(preset="opencode", model="m")
    calls = {"n": 0}

    def fake_run(prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.TimeoutExpired(cmd="opencode", timeout=300)
        return '{"persona":"literalist","score":8,"verdict":"ok","detail":"ok"}'

    monkeypatch.setattr(be, "_run", fake_run)
    v = be.complete("sys", "usr", PersonaVerdict)
    assert calls["n"] == 2 and v.persona == "literalist"


def test_complete_retries_after_cli_exit_error(monkeypatch):
    be = AgentCliBackend(preset="opencode", model="m")
    calls = {"n": 0}

    def fake_run(prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("opencode CLI exited 1: transient")
        return '{"persona":"literalist","score":8,"verdict":"ok","detail":"ok"}'

    monkeypatch.setattr(be, "_run", fake_run)
    assert be.complete("sys", "usr", PersonaVerdict).score == 8


def test_complete_raises_with_cause_after_repeated_timeouts(monkeypatch):
    import subprocess

    be = AgentCliBackend(preset="opencode", model="m")

    def fake_run(prompt):
        raise subprocess.TimeoutExpired(cmd="opencode", timeout=300)

    monkeypatch.setattr(be, "_run", fake_run)
    with pytest.raises(RuntimeError, match="300"):
        be.complete("sys", "usr", PersonaVerdict)
