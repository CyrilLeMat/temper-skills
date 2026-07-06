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


def _module_exists(name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:  # parent package absent (e.g. no `google` at all)
        return False


def _check_vertex_extra(route: str) -> None:
    """Fail fast with install guidance — without this, a missing Vertex dependency
    surfaces four retries later as a raw InstructorRetryException traceback."""
    if not route.startswith("vertex_ai/"):
        return
    missing = [m for m in ("google.auth", "vertexai") if not _module_exists(m)]
    if missing:
        raise RuntimeError(
            f"model {route!r} needs the Vertex extra (missing: {', '.join(missing)}).\n\n"
            "  pip install 'temper-skills[vertex]'\n\n"
            "then authenticate with gcloud ADC (gcloud auth application-default login) "
            "and set VERTEXAI_PROJECT / VERTEXAI_LOCATION."
        )


class ApiBackend(Backend):
    name = "api"

    # temperature is pinned to 0 by default: audit verdicts are meant to be as
    # reproducible as the rubric they feed (default sampling flipped ankle_sprain
    # between TEMPER and DECOMPOSE across identical runs). The loop's diversity
    # comes from distinct persona prompts and the evolving tree/case state, not
    # from sampling noise — raise this only if the loop measurably stalls.
    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 8000,
        temperature: float = 0.0,
    ):
        super().__init__(model)
        import instructor
        import litellm

        import threading

        litellm.suppress_debug_info = True
        self._litellm = litellm
        self._client = instructor.from_litellm(litellm.completion)
        self._route = _route(model)
        _check_vertex_extra(self._route)
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.cost = 0.0
        self._lock = threading.Lock()  # personas run concurrently — guard the counters
        self._warm_lock = threading.Lock()
        self._warmed = False

    def complete(self, system: str, user: str, schema: type[T]) -> T:
        # Instructor registers its provider/mode handlers lazily on the FIRST call;
        # concurrent first calls race that registration and fail with
        # "Mode (...) is not registered. Available modes: []" (seen on `audit <dir>`,
        # where the fan-out makes the very first backend calls concurrent). Serialize
        # until one call has succeeded, then run fully concurrent.
        if not self._warmed:
            with self._warm_lock:
                if not self._warmed:
                    obj = self._complete(system, user, schema)
                    self._warmed = True
                    return obj
        return self._complete(system, user, schema)

    def _complete(self, system: str, user: str, schema: type[T]) -> T:
        obj, completion = self._client.chat.completions.create_with_completion(
            model=self._route,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_model=schema,
            max_retries=2,  # instructor: schema-validation retries
            num_retries=4,  # litellm: transient transport/5xx retries with backoff
            timeout=120,
        )
        usage = getattr(completion, "usage", None)
        try:
            call_cost = self._litellm.completion_cost(completion_response=completion) or 0.0
        except Exception:
            call_cost = 0.0  # unknown-model pricing — best-effort
        with self._lock:
            if usage:
                self.input_tokens += getattr(usage, "prompt_tokens", 0) or 0
                self.output_tokens += getattr(usage, "completion_tokens", 0) or 0
            self.cost += call_cost
        return obj

    def cost_estimate(self) -> float | None:
        return self.cost
