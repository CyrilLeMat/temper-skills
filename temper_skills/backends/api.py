"""ApiBackend — the metered path: Anthropic SDK + native structured outputs."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from .base import Backend

T = TypeVar("T", bound=BaseModel)

# USD per 1M tokens (input, output).
_RATES = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


class ApiBackend(Backend):
    name = "api"

    def __init__(self, model: str = "claude-sonnet-4-6", max_tokens: int = 8000):
        super().__init__(model)
        import anthropic  # imported lazily so the CLI backend needs no SDK key/env

        self.client = anthropic.Anthropic()
        self.max_tokens = max_tokens

    def complete(self, system: str, user: str, schema: type[T]) -> T:
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
                f"Structured parse failed (stop_reason={response.stop_reason}); "
                "the model may have refused or hit max_tokens."
            )
        return parsed

    def cost_estimate(self) -> float | None:
        rin, rout = _RATES.get(self.model, (3.0, 15.0))
        return (self.input_tokens * rin + self.output_tokens * rout) / 1_000_000
