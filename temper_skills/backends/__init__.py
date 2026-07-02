"""Backend selection: API key first, then a runnable agent CLI (§ v1 plan)."""

from __future__ import annotations

import os

from .agent_cli import AgentCliBackend, cli_runs
from .api import ApiBackend
from .base import Backend

__all__ = ["Backend", "ApiBackend", "AgentCliBackend", "get_backend", "auto_backend"]


def get_backend(name: str, model: str | None = None) -> Backend:
    """Build a backend by explicit name: 'api' | 'claude' | 'opencode' | 'auto'."""
    if name == "auto":
        return auto_backend(model)
    if name == "api":
        return ApiBackend(model=model or "claude-sonnet-4-6")
    if name in ("claude", "opencode"):
        return AgentCliBackend(preset=name, model=model or "claude-sonnet-4-6")
    raise ValueError(f"unknown backend {name!r}; choose api | claude | opencode | auto")


def auto_backend(model: str | None = None) -> Backend:
    """Pick a backend: TEMPER_BACKEND override → API key → claude → opencode."""
    override = os.environ.get("TEMPER_BACKEND")
    if override:
        return get_backend(override, model)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ApiBackend(model=model or "claude-sonnet-4-6")
    if cli_runs("claude"):
        return AgentCliBackend(preset="claude", model=model or "claude-sonnet-4-6")
    if cli_runs("opencode"):
        return AgentCliBackend(preset="opencode", model=model or "claude-sonnet-4-6")
    # This error IS onboarding — a cold `uvx temper-skills audit` lands here first.
    raise RuntimeError(
        "no LLM backend detected. Any ONE of these unblocks every command:\n\n"
        "  1. an Anthropic API key      export ANTHROPIC_API_KEY=sk-ant-...\n"
        "  2. the Claude Code CLI       npm install -g @anthropic-ai/claude-code   (run `claude` once to log in)\n"
        "  3. the opencode CLI          https://opencode.ai/docs  (any provider it is logged into)\n\n"
        "then re-run. Force a specific one with --backend api|claude|opencode "
        "(or TEMPER_BACKEND=...)."
    )
