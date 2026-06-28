"""ApiBackend — the metered path, on LiteLLM + Instructor.

LiteLLM routes to any supported provider (Anthropic, OpenAI, Gemini, local, …);
Instructor enforces the Pydantic schema with validation + retries. We don't
re-implement provider integration or structured-output parsing — that's their job.
The loop, personas, export, validation, and incremental code never see this.

Model ids: a bare ``claude-*`` is routed to Anthropic; otherwise pass a LiteLLM
provider-prefixed id (``openai/gpt-4o``, ``gemini/gemini-1.5-pro``, …). The relevant
provider key must be in the environment (ANTHROPIC_API_KEY, OPENAI_API_KEY, …).

Tradeoff vs the old direct-Anthropic backend: Anthropic-specific adaptive thinking is
not requested here (it isn't portable across providers); structured output goes through
Instructor's tool/JSON mode rather than Anthropic's native structured outputs.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from .base import Backend

T = TypeVar("T", bound=BaseModel)


def _route(model: str) -> str:
    """Make a bare model id LiteLLM-routable."""
    if "/" in model:
        return model
    if model.startswith("claude"):
        return f"anthropic/{model}"
    return model


class ApiBackend(Backend):
    name = "api"

    def __init__(self, model: str = "claude-sonnet-4-6", max_tokens: int = 8000):
        super().__init__(model)
        import instructor
        import litellm

        litellm.suppress_debug_info = True
        self._litellm = litellm
        self._client = instructor.from_litellm(litellm.completion)
        self._route = _route(model)
        self.max_tokens = max_tokens
        self.cost = 0.0

    def complete(self, system: str, user: str, schema: type[T]) -> T:
        obj, completion = self._client.chat.completions.create_with_completion(
            model=self._route,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_model=schema,
            max_retries=2,
        )
        usage = getattr(completion, "usage", None)
        if usage:
            self.input_tokens += getattr(usage, "prompt_tokens", 0) or 0
            self.output_tokens += getattr(usage, "completion_tokens", 0) or 0
        try:
            self.cost += self._litellm.completion_cost(completion_response=completion) or 0.0
        except Exception:
            pass  # unknown-model pricing — leave cost as a best-effort sum
        return obj

    def cost_estimate(self) -> float | None:
        return self.cost
