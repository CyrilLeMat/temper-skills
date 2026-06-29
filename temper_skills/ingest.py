"""ingest_skill(): the one-liner entry point for use case #1 — freeze an existing
agent's decision logic (§11.4, Option C hybrid)."""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, Field

from .backends import Backend, auto_backend
from .distill import distill
from .sources import Sources
from .tree import DecisionTree


class InferredFeature(BaseModel):
    name: str
    type: str = Field(description="A JSON-schema type: string, number, integer, boolean.")
    description: str = ""


class InferredSchema(BaseModel):
    fn_name: str = Field(description="A snake_case name for the decision function, e.g. can_dog_eat.")
    features: list[InferredFeature]
    constraints: list[str] = Field(
        default_factory=list,
        description='Hard rules implied by the skill, e.g. "when in doubt, default to no".',
    )


INFER_SYSTEM = (
    "You read an agent skill/prompt and propose the structured features its decision "
    "logic branches on, plus any hard constraints it states. Features must be "
    "pre-computable inputs, not free text evaluated at runtime.\n\n"
    "CRITICAL — features must be RAW, observable properties of the input, never a feature "
    "that restates or presupposes the verdict. Forbidden: any feature that is essentially "
    "the answer — e.g. is_toxic, is_safe, is_known_toxic_food, is_dangerous, is_allowed, "
    "should_block, is_harmful. They are circular: you would already need the decision to "
    "compute them, so the tree collapses to `if is_toxic: unsafe` and learns nothing. "
    "Instead expose the underlying observables the verdict is DERIVED from (the item's "
    "identity/name, its category, quantity, form/preparation, and attributes of the "
    "subject) and let the tree do the deriving. If the skill names specific trigger values "
    "(particular foods, statuses, categories), expose the raw identifier feature (e.g. "
    "food_item) so the tree can enumerate them itself."
)


def _to_json_schema(inferred: InferredSchema) -> dict:
    props = {
        f.name: {"type": f.type, **({"description": f.description} if f.description else {})}
        for f in inferred.features
    }
    return {"type": "object", "properties": props, "additionalProperties": True}


def ingest_skill(
    path: str,
    schema: Any | None = None,
    profile: str = "standard",
    model: str = "claude-sonnet-4-6",
    backend: Backend | None = None,
    gate=None,
    confirm: Callable[[InferredSchema], bool] | None = None,
    fn_name: str | None = None,
    examples: list[dict] | None = None,
    propose_examples: bool = True,
    propose_schema_only: bool = False,
) -> DecisionTree | InferredSchema:
    """Read a skill.md and distill its routing logic into a DecisionTree.

    If ``schema`` is None, one LLM call infers a schema + constraints; ``confirm``
    (if given) is shown the inference and may veto. The ingest call happens once,
    at compile time — distinct from the loop. "Zero LLM at inference" is unaffected.

    If ``propose_schema_only`` is set, the inference is returned without distilling, so
    the caller can persist it for ratification and stop. The loop never runs on an
    unratified schema this way — the contract is drafted, not yet frozen.
    """
    with open(path) as f:
        skill_text = f.read()

    backend = backend or auto_backend(model)
    constraints: list[dict] = []
    resolved_fn = fn_name or "decide"

    if schema is None:
        inferred = backend.complete(
            INFER_SYSTEM,
            f"SKILL:\n{skill_text}\n\nPropose the schema and constraints.",
            InferredSchema,
        )
        if propose_schema_only:
            return inferred
        if confirm is not None and not confirm(inferred):
            raise KeyboardInterrupt("schema rejected at ingest gate")
        schema = _to_json_schema(inferred)
        constraints = [{"rule": c, "hard": True} for c in inferred.constraints]
        resolved_fn = fn_name or inferred.fn_name
    elif isinstance(schema, type) and issubclass(schema, BaseModel):
        resolved_fn = fn_name or "decide"

    sources = Sources(schema=schema, constraints=constraints, skill_text=skill_text,
                      examples=examples or [])
    return distill(
        sources, profile=profile, backend=backend, gate=gate, fn_name=resolved_fn,
        propose_examples=propose_examples,
    )
