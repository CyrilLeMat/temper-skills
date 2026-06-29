"""Split a big skill (a *flow*) into its distinct decision points.

temper operates on a *decision*, not a *skill*. A large skill is a flow = a graph of
{decisions + generation + orchestration}. There isn't one decision function to freeze —
there are several, plus glue. This pass segments the flow so each decision can be audited
and tempered on its own, leaving the orchestration/generation to the model (DMN-vs-BPMN:
factor the decision logic out of the process).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .audit import (
    AUDIT_SYSTEM,
    FitnessReport,
    JudgeScores,
    open_features,
    recommend_action,
    schema_closure,
    verdict_of,
)
from .backends import Backend, auto_backend
from .ingest import InferredFeature, InferredSchema


class CandidateDecision(BaseModel):
    fn_name: str = Field(description="snake_case name for THIS decision, e.g. decide_escalation.")
    description: str = Field(description="the one decision this node makes.")
    features: list[InferredFeature] = Field(
        default_factory=list, description="the mini-schema feeding ONLY this decision."
    )
    outcomes: list[str] = Field(default_factory=list, description="its finite output labels.")
    consumes: list[str] = Field(
        default_factory=list,
        description="fn_names of OTHER decisions whose output feeds this one (coupling edges).",
    )


class Decomposition(BaseModel):
    decisions: list[CandidateDecision] = Field(default_factory=list)
    generative_steps: list[str] = Field(
        default_factory=list,
        description="parts that are open-ended generation / pure orchestration, NOT decisions.",
    )


DECOMPOSE_SYSTEM = (
    "You split an agent skill into its distinct DECISION points. A decision resolves to a "
    "finite set of outcomes from a bounded set of features. For each, give a snake_case "
    "name, the features feeding ONLY it, and its outcome labels. List parts that are "
    "open-ended generation or pure orchestration separately as generative_steps — do NOT "
    "model them as decisions. Record coupling: if decision B branches on the OUTPUT of "
    "decision A, put A in B.consumes. Prefer FEW, cohesive decisions: if two candidates "
    "share most features and always co-occur, they are ONE decision — merge them. Don't "
    "over-split."
)


def decompose_skill(path: str, backend: Backend | None = None,
                    model: str = "claude-sonnet-4-6") -> Decomposition:
    """One LLM turn: segment a skill into its decision points + generative steps."""
    backend = backend or auto_backend(model)
    with open(path) as f:
        text = f.read()
    return backend.complete(DECOMPOSE_SYSTEM, f"SKILL:\n{text}", Decomposition)


def audit_decision(d: CandidateDecision, backend: Backend) -> FitnessReport:
    """Audit a single extracted decision — judges from its description + mini-schema, with
    no separate file to read (the flow's prose was already consumed by decompose_skill)."""
    schema = InferredSchema(fn_name=d.fn_name, features=d.features)
    j = backend.complete(
        AUDIT_SYSTEM,
        f"DECISION: {d.description}\nOUTCOMES: {d.outcomes}\n\nScore the three axes.",
        JudgeScores,
    )
    closure = schema_closure(schema)
    opens = open_features(schema)
    verdict, reasons, caveats = verdict_of(j, closure, len(schema.features))
    action = recommend_action(j, opens)
    return FitnessReport(
        fn_name=d.fn_name,
        verdict=verdict,
        decisiveness=j.decisiveness,
        combinatorics=j.combinatorics,
        stakes=j.stakes,
        schema_closure=closure,
        open_features=opens,
        n_features=len(d.features),
        rationale=j.rationale,
        recommended_action=action,
        reasons=reasons,
        caveats=caveats,
    )


def coupling(decomp: Decomposition) -> dict[str, str]:
    """Per decision: 'independent' (temper standalone) or 'consumes …' (the orchestrator
    must feed it an upstream tree's output — the coupling we accept rather than deny)."""
    return {
        d.fn_name: "independent" if not d.consumes else f"consumes {', '.join(d.consumes)}"
        for d in decomp.decisions
    }
