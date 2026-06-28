"""Thin wrapper over the Anthropic SDK for the loop's structured calls.

Every loop call forces a Pydantic schema via structured outputs, so the proposer
and personas return validated objects rather than free text — the basis for the
machine-parseable arbitrage log (§5.5).
"""

from __future__ import annotations

from typing import TypeVar

import anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# Cost framing for §4.2 estimates (USD per 1M tokens, input/output):
#   claude-sonnet-4-6  $3 / $15
#   claude-opus-4-8    $5 / $25
#   claude-haiku-4-5   $1 / $5
DEFAULT_MODEL = "claude-sonnet-4-6"


class LLM:
    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 8000):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens
        self.input_tokens = 0
        self.output_tokens = 0

    def parse(self, system: str, user: str, schema: type[T]) -> T:
        """One structured call. Returns a validated instance of ``schema``."""
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        parsed = response.parsed_output
        if parsed is None:
            raise RuntimeError(
                f"Structured parse failed (stop_reason={response.stop_reason}). "
                "The model may have refused or hit max_tokens."
            )
        return parsed

    def cost_estimate(self, model: str | None = None) -> float:
        """Rough USD cost of all calls so far, for the per-profile estimate."""
        rates = {
            "claude-sonnet-4-6": (3.0, 15.0),
            "claude-opus-4-8": (5.0, 25.0),
            "claude-haiku-4-5": (1.0, 5.0),
        }
        rin, rout = rates.get(model or self.model, (3.0, 15.0))
        return (self.input_tokens * rin + self.output_tokens * rout) / 1_000_000
