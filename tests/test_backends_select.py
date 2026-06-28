"""auto_backend selection order and get_backend dispatch."""

from __future__ import annotations

import pytest

from temper_skills import backends
from temper_skills.backends import auto_backend, get_backend


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("TEMPER_BACKEND", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_api_key_first(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert auto_backend().name == "api"


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("TEMPER_BACKEND", "opencode")
    assert auto_backend().name == "opencode"


def test_falls_back_to_runnable_cli_skipping_crash(monkeypatch):
    # no API key; claude "crashes", opencode runs
    monkeypatch.setattr(backends, "cli_runs", lambda name: name == "opencode")
    be = auto_backend()
    assert be.name == "opencode"


def test_prefers_claude_when_it_runs(monkeypatch):
    monkeypatch.setattr(backends, "cli_runs", lambda name: True)
    assert auto_backend().name == "claude"


def test_raises_when_nothing_available(monkeypatch):
    monkeypatch.setattr(backends, "cli_runs", lambda name: False)
    with pytest.raises(RuntimeError):
        auto_backend()


def test_get_backend_names(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert get_backend("api").name == "api"
    assert get_backend("claude").name == "claude"
    assert get_backend("opencode").name == "opencode"


def test_get_backend_invalid():
    with pytest.raises(ValueError):
        get_backend("bogus")
