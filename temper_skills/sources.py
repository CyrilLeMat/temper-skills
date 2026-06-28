"""Input types: the anchoring levers a user provides to the loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


@dataclass
class Persona:
    """An adversarial reviewer that challenges the proposed tree from one angle."""

    name: str
    style: str


# The four attackers plus the always-on structural counterweight (§5.5).
LITERALIST = Persona("literalist", "exploits literal ambiguities in the schema")
EDGE_CASE_HUNTER = Persona("edge_case_hunter", "seeks rare combinations of feature values")
BAD_FAITH_ACTOR = Persona("bad_faith_actor", "tries to strategically circumvent the rule")
DOMAIN_EXPERT = Persona("domain_expert", "tests with rare but plausible domain cases")
OVERENGINEERING_CRITIC = Persona(
    "overengineering_critic",
    "challenges every node: is this branch actually necessary, or is it loop richness "
    "rather than domain complexity?",
)

DEFAULT_PERSONAS: list[Persona] = [
    LITERALIST,
    EDGE_CASE_HUNTER,
    BAD_FAITH_ACTOR,
    DOMAIN_EXPERT,
]


def _normalize_schema(schema: Any) -> dict:
    """Accept a Pydantic model class or a raw JSON Schema dict; return JSON Schema."""
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return schema.model_json_schema()
    if isinstance(schema, dict):
        return schema
    raise TypeError(
        "schema must be a Pydantic BaseModel subclass or a JSON Schema dict, "
        f"got {type(schema)!r}"
    )


@dataclass
class Sources:
    """The three anchoring levers. Only ``schema`` is required (§4.1).

    ``schema``      pre-computed structured features the tree branches on.
    ``constraints`` non-negotiable rules: ``[{"rule": str, "hard": bool}]``.
    ``examples``    a few ratified cases: ``[{"input": dict, "expected": str}]``.
    """

    schema: Any
    constraints: list[dict] = field(default_factory=list)
    examples: list[dict] = field(default_factory=list)
    skill_text: str | None = None  # the original skill.md logic being migrated

    def __post_init__(self) -> None:
        self.json_schema = _normalize_schema(self.schema)

    @property
    def feature_names(self) -> list[str]:
        return list(self.json_schema.get("properties", {}).keys())
