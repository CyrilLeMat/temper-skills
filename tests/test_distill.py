"""The adversarial loop, driven by a scripted FakeBackend (no network)."""

from __future__ import annotations

import pytest
from conftest import FakeBackend, TicketSchema

from temper_skills import LITERALIST, Sources, distill


def _sources():
    return Sources(schema=TicketSchema, constraints=[{"rule": "x", "hard": True}])


def test_returns_tree_with_metadata():
    be = FakeBackend(score=9)
    tree = distill(_sources(), backend=be, profile="quick", fn_name="route_ticket")
    assert tree.fn_name == "route_ticket"
    assert tree.features == ["priority", "security_score"]
    assert tree.default_outcome == "route_default"
    assert tree.model == "fake-model via fake"


def test_overengineering_critic_always_added():
    be = FakeBackend(score=9)
    distill(_sources(), adversaries=[LITERALIST], backend=be, profile="quick")
    seen = set(be.personas_seen)
    assert "literalist" in seen
    assert "overengineering_critic" in seen


def test_high_scores_converge_early():
    be = FakeBackend(score=9)  # settled every round; quick stop_quiet=2
    distill(_sources(), backend=be, profile="quick")
    assert be.calls["arbitration"] == 2  # converged at round 2, well under the cap of 8


def test_low_scores_run_to_cap():
    be = FakeBackend(score=3)  # never clears the bar -> never settles
    distill(_sources(), backend=be, profile="quick")
    assert be.calls["arbitration"] == 8  # quick profile max rounds


def test_rounds_survived_tracked():
    be = FakeBackend(score=9)
    tree = distill(_sources(), backend=be, profile="quick")
    # initial draft (1) + 2 surviving rounds
    assert tree.nodes[0].rounds_survived == 3


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
