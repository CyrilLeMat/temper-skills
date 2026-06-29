"""Splitting a flow-shaped skill into its decision points (no network)."""

from __future__ import annotations

from temper_skills.audit import JudgeScores
from temper_skills.backends.base import Backend
from temper_skills.decompose import (
    CandidateDecision,
    Decomposition,
    audit_decision,
    coupling,
    decompose_skill,
)
from temper_skills.ingest import InferredFeature


def _feat(name, type="string", desc=""):
    return InferredFeature(name=name, type=type, description=desc)


_DECOMP = Decomposition(
    decisions=[
        CandidateDecision(fn_name="classify_ticket", description="bucket the ticket",
                          features=[_feat("category", desc="one of billing, bug, other")],
                          outcomes=["billing", "bug", "other"]),
        CandidateDecision(fn_name="decide_escalation", description="escalate or not",
                          features=[_feat("priority", desc="one of low, high"),
                                    _feat("category", desc="one of billing, bug, other")],
                          outcomes=["escalate", "route"], consumes=["classify_ticket"]),
    ],
    generative_steps=["draft the customer-facing reply"],
)


class _Be(Backend):
    name = "fake"

    def __init__(self, decomp=_DECOMP, scores=None):
        super().__init__("fake-model")
        self._decomp = decomp
        self._scores = scores or JudgeScores(decisiveness=8, combinatorics=7, stakes=6)

    def complete(self, system, user, schema):
        if schema is Decomposition:
            return self._decomp
        if schema is JudgeScores:
            return self._scores
        raise AssertionError(f"unexpected schema {schema}")


def test_decompose_skill_returns_decisions_and_generative(tmp_path):
    skill = tmp_path / "skill.md"
    skill.write_text("# a support flow that classifies, escalates, and replies")
    decomp = decompose_skill(str(skill), backend=_Be())
    assert [d.fn_name for d in decomp.decisions] == ["classify_ticket", "decide_escalation"]
    assert decomp.generative_steps == ["draft the customer-facing reply"]


def test_coupling_marks_independent_and_chained():
    c = coupling(_DECOMP)
    assert c["classify_ticket"] == "independent"
    assert c["decide_escalation"] == "consumes classify_ticket"


def test_audit_decision_judges_from_mini_schema():
    d = _DECOMP.decisions[1]  # decide_escalation: two closed enums
    report = audit_decision(d, _Be(scores=JudgeScores(decisiveness=9, combinatorics=7, stakes=6)))
    assert report.fn_name == "decide_escalation"
    assert report.verdict == "temper"          # decisive, closed schema
    assert report.schema_closure == 1.0
    assert report.n_features == 2


def test_audit_decision_flags_open_text_field():
    d = CandidateDecision(fn_name="decide_refund", description="refund eligibility",
                          features=[_feat("customer_note", desc="free text from the customer")],
                          outcomes=["refund", "deny"])
    report = audit_decision(d, _Be(scores=JudgeScores(decisiveness=8, combinatorics=4, stakes=5)))
    assert report.open_features == ["customer_note"]
    assert report.verdict == "caveats"          # half-open / borderline, not a clean temper
