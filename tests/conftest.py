"""Shared test fixtures — a FakeBackend that drives the loop without any network."""

from __future__ import annotations

import re

from pydantic import BaseModel

from temper_skills.backends.base import Backend
from temper_skills.ingest import InferredFeature, InferredSchema
from temper_skills.schemas import (
    ArbitrationEntry,
    PersonaVerdict,
    ProposedNode,
    ProposedTree,
    ProposerArbitration,
)


class TicketSchema(BaseModel):
    priority: str
    security_score: float


_TREE = ProposedTree(
    nodes=[
        ProposedNode(
            condition='priority == "high"',
            outcome="escalate_urgent",
            sources=["constraints#1"],
            gray_zone=None,
        )
    ],
    default_outcome="route_default",
)


class FakeBackend(Backend):
    """Returns scripted, schema-valid objects. ``score`` drives convergence;
    records which personas were asked to critique."""

    name = "fake"

    def __init__(self, score: int = 9):
        super().__init__("fake-model")
        self.score = score
        self.personas_seen: list[str] = []
        self.calls = {"tree": 0, "verdict": 0, "arbitration": 0, "inferred": 0}

    def complete(self, system: str, user: str, schema):
        if schema is ProposedTree:
            self.calls["tree"] += 1
            return _TREE
        if schema is PersonaVerdict:
            self.calls["verdict"] += 1
            m = re.search(r"Your angle \((\w+)\)", user)
            persona = m.group(1) if m else "unknown"
            self.personas_seen.append(persona)
            return PersonaVerdict(
                persona=persona, score=self.score, verdict="ok", detail="fine"
            )
        if schema is ProposerArbitration:
            self.calls["arbitration"] += 1
            return ProposerArbitration(
                entries=[ArbitrationEntry(persona="literalist", decision="kept", rationale="ok")],
                convergence_estimate=90,
                tree=_TREE,
            )
        if schema is InferredSchema:
            self.calls["inferred"] += 1
            return InferredSchema(
                fn_name="route_ticket",
                features=[
                    InferredFeature(name="priority", type="string"),
                    InferredFeature(name="security_score", type="number"),
                ],
                constraints=["when in doubt, human_review"],
            )
        raise AssertionError(f"unexpected schema {schema}")
