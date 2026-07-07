"""ApiBackend: LiteLLM routing, token/cost accounting (client stubbed, no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from temper_skills.backends import api
from temper_skills.backends.api import ApiBackend, _route
from temper_skills.schemas import PersonaVerdict


def test_route_qualifies_bare_ids():
    assert _route("claude-sonnet-4-6") == "anthropic/claude-sonnet-4-6"
    assert _route("vertex_ai/claude-sonnet-4-6") == "vertex_ai/claude-sonnet-4-6"
    assert _route("gpt-4o") == "gpt-4o"


def _stub_client(obj, usage, calls=None):
    completion = SimpleNamespace(usage=usage)

    def create(**kw):
        if calls is not None:
            calls.append(kw)
        return obj, completion

    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create_with_completion=create))
    )


def test_complete_accumulates_tokens_and_cost():
    be = ApiBackend(model="claude-sonnet-4-6")
    verdict = PersonaVerdict(persona="literalist", score=8, verdict="ok", detail="d")
    be._client = _stub_client(verdict, SimpleNamespace(prompt_tokens=100, completion_tokens=40))
    be._litellm = SimpleNamespace(completion_cost=lambda completion_response: 0.002)

    got = be.complete("sys", "usr", PersonaVerdict)
    assert got is verdict
    assert be.input_tokens == 100 and be.output_tokens == 40
    assert be.cost_estimate() == 0.002


def test_complete_survives_unknown_model_pricing():
    be = ApiBackend(model="claude-sonnet-4-6")
    verdict = PersonaVerdict(persona="literalist", score=8, verdict="ok", detail="d")
    be._client = _stub_client(verdict, usage=None)

    def boom(completion_response):
        raise ValueError("unknown model")

    be._litellm = SimpleNamespace(completion_cost=boom)
    assert be.complete("sys", "usr", PersonaVerdict) is verdict
    assert be.cost_estimate() == 0.0


def test_temperature_pinned_to_zero_by_default():
    # Default sampling flipped audit verdicts (TEMPER vs DECOMPOSE) across
    # identical runs — the completion call must pin temperature.
    be = ApiBackend(model="claude-sonnet-4-6")
    verdict = PersonaVerdict(persona="literalist", score=8, verdict="ok", detail="d")
    calls: list[dict] = []
    be._client = _stub_client(verdict, usage=None, calls=calls)
    be._litellm = SimpleNamespace(completion_cost=lambda completion_response: 0.0)

    be.complete("sys", "usr", PersonaVerdict)
    assert calls[0]["temperature"] == 0.0


def test_temperature_override_passes_through():
    be = ApiBackend(model="claude-sonnet-4-6", temperature=0.7)
    verdict = PersonaVerdict(persona="literalist", score=8, verdict="ok", detail="d")
    calls: list[dict] = []
    be._client = _stub_client(verdict, usage=None, calls=calls)
    be._litellm = SimpleNamespace(completion_cost=lambda completion_response: 0.0)

    be.complete("sys", "usr", PersonaVerdict)
    assert calls[0]["temperature"] == 0.7


def test_vertex_model_without_extra_fails_fast_with_guidance(monkeypatch):
    monkeypatch.setattr(api, "_module_exists", lambda name: False)
    with pytest.raises(RuntimeError, match=r"temper-skills\[vertex\]"):
        ApiBackend(model="vertex_ai/claude-sonnet-4-6")


def test_non_vertex_model_skips_the_extra_check(monkeypatch):
    def boom(name):
        raise AssertionError("dependency probe must not run for non-vertex models")

    monkeypatch.setattr(api, "_module_exists", boom)
    ApiBackend(model="claude-sonnet-4-6")


def test_vertex_model_with_extra_constructs(monkeypatch):
    monkeypatch.setattr(api, "_module_exists", lambda name: True)
    ApiBackend(model="vertex_ai/claude-sonnet-4-6")
