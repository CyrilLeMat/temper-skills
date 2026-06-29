"""Splitting a flow-shaped skill into its decision points (no network)."""

from __future__ import annotations

from conftest import FakeBackend

from temper_skills import cli
from temper_skills.audit import JudgeScores
from temper_skills.backends.base import Backend
from temper_skills.decompose import (
    CandidateDecision,
    Decomposition,
    audit_decision,
    coupling,
    decompose_skill,
)
from temper_skills.ingest import InferredFeature, InferredSchema


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


# ---- --temper-each end-to-end through the CLI (no network) ----

class _FullBe(FakeBackend):
    """Decomposition + JudgeScores on top of FakeBackend's distill-loop schemas."""

    def __init__(self, decomp=_DECOMP):
        super().__init__(score=9)
        self._decomp = decomp

    def complete(self, system, user, schema):
        if schema is Decomposition:
            return self._decomp
        if schema is JudgeScores:
            return JudgeScores(decisiveness=8, combinatorics=7, stakes=6)
        return super().complete(system, user, schema)


def _write_skill(tmp_path):
    p = tmp_path / "skill.md"
    p.write_text("# a flow: classify the ticket, then decide escalation")
    return str(p)


def test_temper_each_emits_then_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_backend", lambda *a, **k: _FullBe())
    skill = _write_skill(tmp_path)
    cli.decompose(skill=skill, model="x", backend="auto", emit_schemas=False,
                  temper_each=True, yes_unratified=False, profile="quick",
                  out_dir=str(tmp_path), json_out=False)
    # schemas + persisted plan written; NO trees yet (it stopped for ratification)
    assert (tmp_path / "classify_ticket.schema.py").exists()
    assert (tmp_path / "decide_escalation.schema.py").exists()
    assert (tmp_path / "decomposition.json").exists()
    assert not (tmp_path / "classify_ticket.py").exists()


def test_temper_each_compiles_trees_and_orchestrator(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_backend", lambda *a, **k: _FullBe())
    skill = _write_skill(tmp_path)
    # 1st call emits + stops; 2nd call finds the (now-existing) schemas → compiles
    cli.decompose(skill=skill, model="x", backend="auto", emit_schemas=False, temper_each=True,
                  yes_unratified=False, profile="quick", out_dir=str(tmp_path), json_out=False)
    cli.decompose(skill=skill, model="x", backend="auto", emit_schemas=False, temper_each=True,
                  yes_unratified=False, profile="quick", out_dir=str(tmp_path), json_out=False)
    assert (tmp_path / "classify_ticket.py").exists()
    assert (tmp_path / "decide_escalation.py").exists()
    orch = tmp_path / "skill.tempered.md"
    assert orch.exists()
    text = orch.read_text()
    assert "classify_ticket" in text and "decide_escalation" in text
    assert "consumes" in text.lower() or "chain" in text.lower()   # coupling surfaced


# ---- guide: the one-command end-to-end demo (no network, non-tty) ----

class _GuideBe(FakeBackend):
    """audit → a single closed-schema decision routed to `temper`, then the distill loop."""

    def complete(self, system, user, schema):
        if schema is JudgeScores:
            return JudgeScores(decisiveness=9, combinatorics=8, stakes=8, distinct_decisions=1)
        if schema is InferredSchema:
            return InferredSchema(fn_name="route_ticket", features=[
                InferredFeature(name="priority", type="string", description="one of low, high"),
                InferredFeature(name="security_score", type="number"),
            ])
        return super().complete(system, user, schema)


def test_guide_audits_then_tempers_to_a_full_skill(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_backend", lambda *a, **k: _GuideBe(score=9))
    skill = tmp_path / "skill.md"
    skill.write_text("# route a ticket by priority and security")
    # non-tty: the [1] prompts are skipped, the guide runs straight through the temper route
    cli.guide(skill=str(skill), model="x", backend="auto", profile="quick", out_dir=str(tmp_path))
    assert (tmp_path / "route_ticket.py").exists()
    assert (tmp_path / "route_ticket.tempered.md").exists()
