"""The adversarial loop, driven by a scripted FakeBackend (no network)."""

from __future__ import annotations

import pytest
from conftest import FakeBackend, TicketSchema

from temper_skills import DOMAIN_EXPERT, EDGE_CASE_HUNTER, LITERALIST, Sources, distill


def _sources():
    return Sources(schema=TicketSchema, constraints=[{"rule": "x", "hard": True}])


def test_returns_tree_with_metadata():
    be = FakeBackend(score=9)
    tree = distill(_sources(), backend=be, profile="quick", fn_name="route_ticket")
    assert tree.fn_name == "route_ticket"
    assert tree.features == ["priority", "security_score"]
    assert tree.default_outcome == "route_default"
    assert tree.model == "fake-model via fake"


def test_persona_panel_scales_with_profile():
    for profile, total in [("quick", 2), ("standard", 3), ("audit-grade", 5)]:
        be = FakeBackend(score=9)
        distill(_sources(), backend=be, profile=profile, gate=lambda r: "stop")
        seen = set(be.personas_seen)  # round-1 panel before the gate stops it
        assert "overengineering_critic" in seen
        assert len(seen) == total, (profile, seen)


def test_overengineering_critic_always_added():
    be = FakeBackend(score=9)
    distill(_sources(), adversaries=[LITERALIST], backend=be, profile="quick")
    seen = set(be.personas_seen)
    assert "literalist" in seen
    assert "overengineering_critic" in seen


def test_stable_scores_plateau_and_stop():
    # FakeBackend returns the same tree+scores every round, so after the first
    # round nothing improves — the loop plateaus and stops (quick stop_quiet=2):
    # round 1 (progress) → rounds 2,3 stale → stop at round 3.
    be = FakeBackend(score=9)
    distill(_sources(), backend=be, profile="quick")
    assert be.calls["arbitration"] == 3


def test_stuck_low_scores_also_stop_on_plateau():
    # The old behavior ground to the round cap; now a stuck run stops on plateau too.
    be = FakeBackend(score=3)
    distill(_sources(), backend=be, profile="quick")
    assert be.calls["arbitration"] == 3  # not the cap of 8


def test_backend_failure_after_progress_salvages_last_tree():
    be = FakeBackend(score=4)
    orig = be.complete
    calls = {"n": 0}

    def flaky(system, user, schema):
        from temper_skills.schemas import ProposerArbitration
        if schema is ProposerArbitration:
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("transient backend disconnect")
        return orig(system, user, schema)

    be.complete = flaky
    # round 1 arbitration ok, round 2 arbitration raises → salvage round-1 tree
    tree = distill(_sources(), backend=be, profile="standard")
    assert tree.nodes  # finalized the last good tree instead of crashing


def test_rounds_survived_tracked():
    be = FakeBackend(score=9)
    tree = distill(_sources(), backend=be, profile="quick")
    # initial draft (1) + 3 surviving rounds (plateau stop at round 3)
    assert tree.nodes[0].rounds_survived == 4


def test_quick_profile_no_provenance():
    be = FakeBackend(score=9)
    tree = distill(_sources(), backend=be, profile="quick")
    assert tree.include_provenance is False


def test_gate_stop_breaks_early():
    be = FakeBackend(score=9)
    distill(_sources(), backend=be, profile="standard", gate=lambda r: "stop")
    assert be.calls["arbitration"] == 1


def test_gate_abort_raises():
    be = FakeBackend(score=9)
    with pytest.raises(KeyboardInterrupt):
        distill(_sources(), backend=be, profile="standard", gate=lambda r: "abort")


def test_unknown_profile_rejected():
    with pytest.raises(ValueError):
        distill(_sources(), backend=FakeBackend(), profile="nope")


def test_no_examples_means_no_report():
    tree = distill(_sources(), backend=FakeBackend(score=9), profile="quick")
    assert tree.example_report is None


def test_ratified_examples_checked_and_agree():
    src = Sources(schema=TicketSchema, examples=[
        {"input": {"priority": "high", "security_score": 0.1}, "expected": "escalate_urgent"},
    ])
    tree = distill(src, backend=FakeBackend(score=9), profile="quick")
    assert tree.example_report is not None
    assert tree.example_report.total == 1
    assert tree.example_report.disagreements == []


def _node_tree(condition, outcome, gray_zone=None):
    from temper_skills.schemas import ProposedNode, ProposedTree
    return ProposedTree(
        nodes=[ProposedNode(condition=condition, outcome=outcome, sources=["c#1"], gray_zone=gray_zone)],
        default_outcome="route_default",
    )


def test_buzzer_beating_regression_is_not_shipped():
    """A late round that breaks a ratified example must NOT be the finalized tree.

    Reproduces the observed failure: the loop reached a tree passing all examples,
    then a later round reordered nodes in a way that broke one — and that broken tree
    got exported. distill must finalize the best tree it ever saw, not the last one.
    """
    from conftest import ScriptedBackend

    passing = _node_tree("security_score is not None and security_score >= 0.95", "human_review")
    regressed = _node_tree('(priority or "").strip().lower() == "high"', "escalate_urgent")
    be = ScriptedBackend(trees=[passing, regressed, regressed, regressed], scores=[5])

    src = Sources(schema=TicketSchema, examples=[
        {"input": {"priority": "high", "security_score": 0.99}, "expected": "human_review"},
    ])
    tree = distill(src, backend=be, profile="quick", fn_name="route_ticket")
    assert tree.example_report.agreement_rate == 1.0
    assert tree.nodes[0].outcome == "human_review"  # the passing tree, not escalate_urgent


def test_gray_zone_churn_does_not_block_plateau():
    """The exact shape of bug #2: the tree's logic is settled but each round emits a
    freshly-worded gray zone. That used to read as 'progress' and burn every round.
    With no score/agreement gain it must plateau (quick: stop at round 3, not cap 8)."""
    from conftest import ScriptedBackend

    churn = [_node_tree('priority == "high"', "escalate_urgent", gray_zone=f"reworded zone {i}")
             for i in range(1, 9)]
    be = ScriptedBackend(trees=churn, scores=[6])
    distill(_sources(), backend=be, profile="quick")
    assert be.calls["arbitration"] == 3


def test_genuine_score_improvement_extends_then_plateaus():
    """The flip side of the plateau fix: a real, rising score is progress and keeps the
    loop going; once the score goes flat it plateaus. Guards against over-eager stopping."""
    from conftest import ScriptedBackend

    be = ScriptedBackend(trees=[_node_tree('priority == "high"', "escalate_urgent")],
                         scores=[5, 6, 7, 7, 7, 7, 7, 7])
    distill(_sources(), backend=be, profile="quick")
    assert be.calls["arbitration"] == 5  # rose through r1-3, flat r4-5 → plateau at 5


def test_proposed_examples_on_by_default():
    # Always produce a proposed validation set, even with no input examples (req 1).
    tree = distill(_sources(), backend=FakeBackend(score=9), profile="quick",
                   fn_name="route_ticket")
    assert tree.proposed_examples is not None
    p = tree.proposed_examples[0]
    assert p["status"] == "proposed"           # never silently ratified
    assert "tree_prediction" in p              # what the frozen tree actually returns


def test_propose_examples_can_be_disabled():
    tree = distill(_sources(), backend=FakeBackend(score=9), profile="quick",
                   propose_examples=False)
    assert tree.proposed_examples is None


def test_proposed_examples_dedup_against_ratified():
    # FakeBackend (fallback path) proposes a case whose input duplicates a ratified
    # example — it must be dropped, leaving only the genuinely new one.
    src = Sources(schema=TicketSchema, examples=[
        {"input": {"priority": "high", "security_score": 0.1}, "expected": "escalate_urgent"},
    ])
    tree = distill(src, backend=FakeBackend(score=9), profile="quick",
                   fn_name="route_ticket")
    inputs = [p["input"] for p in tree.proposed_examples]
    assert {"priority": "high", "security_score": 0.1} not in inputs
    assert len(tree.proposed_examples) == 1


def test_personas_build_validation_set_excluding_critic():
    """Req 2: every persona except the overengineering_critic contributes cases, and they
    accumulate (deduped) across rounds into the proposed set — no extra generation call."""
    import re
    from temper_skills.backends.base import Backend
    from temper_skills.schemas import (
        ArbitrationEntry, PersonaVerdict, ProposedExample, ProposedExampleSet,
        ProposedNode, ProposedTree, ProposerArbitration,
    )

    tree = ProposedTree(
        nodes=[ProposedNode(condition='priority == "high"', outcome="escalate_urgent")],
        default_outcome="route_default")

    class PanelBackend(Backend):
        name = "fake"

        def __init__(self):
            super().__init__("fake-model")

        def complete(self, system, user, schema):
            if schema is ProposedTree:
                return tree
            if schema is PersonaVerdict:
                p = re.search(r"Your angle \((\w+)\)", user).group(1)
                # EVERY persona (even the critic) emits a case keyed by its own name;
                # the critic's must be dropped by the harvester regardless.
                return PersonaVerdict(
                    persona=p, score=9, verdict="ok", detail="d",
                    proposed_tests=[ProposedExample(
                        input={"priority": p, "security_score": 0.5},
                        expected="human_review", rationale=f"{p} case")])
            if schema is ProposerArbitration:
                return ProposerArbitration(
                    entries=[ArbitrationEntry(persona="x", decision="kept", rationale="ok")],
                    convergence_estimate=95, tree=tree)
            if schema is ProposedExampleSet:
                return ProposedExampleSet(examples=[])  # fallback must not be needed
            raise AssertionError(schema)

    t = distill(_sources(), backend=PanelBackend(), profile="standard", fn_name="route_ticket",
                adversaries=[EDGE_CASE_HUNTER, DOMAIN_EXPERT])
    by_input = {p["input"]["priority"] for p in t.proposed_examples}
    assert "overengineering_critic" not in by_input          # critic contributes nothing
    assert {"edge_case_hunter", "domain_expert"} <= by_input  # the attackers do
    assert all(p["status"] == "proposed" for p in t.proposed_examples)
    # same input each round → deduped to one entry per persona
    assert len(t.proposed_examples) == len(by_input)


def test_ratified_example_disagreement_surfaced():
    # FakeBackend's tree routes only priority=="high"; a low-priority example that
    # expects escalate_urgent must surface as a disagreement.
    src = Sources(schema=TicketSchema, examples=[
        {"input": {"priority": "low", "security_score": 0.1}, "expected": "escalate_urgent"},
    ])
    tree = distill(src, backend=FakeBackend(score=9), profile="quick")
    rep = tree.example_report
    assert rep.agreements == 0 and len(rep.disagreements) == 1
    assert rep.disagreements[0].predicted == "route_default"
