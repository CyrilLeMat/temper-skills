"""Incremental mode: structural diff + recrystallize from a seed tree."""

from __future__ import annotations

from conftest import FakeBackend, TicketSchema

from temper_skills import Sources, diff_trees, recrystallize
from temper_skills.tree import DecisionNode, DecisionTree


def _tree(nodes, default="route_default"):
    return DecisionTree(nodes=nodes, default_outcome=default,
                        features=["priority", "security_score"], fn_name="route_ticket")


def test_diff_detects_added_removed_changed_unchanged():
    old = _tree([
        DecisionNode('priority == "high"', "escalate_urgent"),
        DecisionNode('security_score > 0.8', "escalate_security"),
    ])
    new = _tree([
        DecisionNode('priority == "high"', "escalate_urgent"),            # unchanged
        DecisionNode('security_score > 0.8', "human_review"),             # changed outcome
        DecisionNode('priority == "low"', "route_low"),                   # added
    ], default="route_default")
    d = diff_trees(old, new)
    assert [n.condition for n in d.unchanged] == ['priority == "high"']
    assert [n.condition for n in d.added] == ['priority == "low"']
    assert [(o.outcome, n.outcome) for o, n in d.changed] == [("escalate_security", "human_review")]
    # security_score node persisted (changed), nothing removed
    assert d.removed == []
    assert not d.is_empty


def test_diff_detects_default_change_and_removal():
    old = _tree([DecisionNode('priority == "high"', "a"), DecisionNode('priority == "low"', "b")])
    new = _tree([DecisionNode('priority == "high"', "a")], default="new_default")
    d = diff_trees(old, new)
    assert [n.condition for n in d.removed] == ['priority == "low"']
    assert d.default_change == ("route_default", "new_default")


def test_empty_diff():
    t = _tree([DecisionNode('priority == "high"', "a")])
    assert diff_trees(t, _tree([DecisionNode('priority == "high"', "a")])).is_empty


def test_recrystallize_seeds_and_carries_survival():
    # prior overlaps the FakeBackend's canned tree (priority=="high" node) plus an extra node
    prior = _tree([
        DecisionNode('priority == "high"', "escalate_urgent", rounds_survived=9, sources=["old"]),
        DecisionNode('security_score > 0.99', "stale_branch", rounds_survived=4),
    ])
    be = FakeBackend(score=9)
    sources = Sources(schema=TicketSchema, constraints=[{"rule": "new rule", "hard": True}])
    new_tree, diff = recrystallize(prior, sources, backend=be, profile="quick")

    # FakeBackend never drafts an initial tree in incremental mode
    assert be.calls["tree"] == 0
    # the shared node survived (seed survival 9 + 3 rounds to plateau = 12)
    kept = next(n for n in new_tree.nodes if n.condition == 'priority == "high"')
    assert kept.rounds_survived == 12
    # the stale branch the new tree dropped shows up as removed
    assert [n.condition for n in diff.removed] == ['security_score > 0.99']


def test_render_diff_lists_every_change_kind():
    from temper_skills.incremental import render_diff

    old = _tree([
        DecisionNode('priority == "high"', "escalate_urgent"),
        DecisionNode('security_score > 0.8', "escalate_security"),
        DecisionNode('priority == "spam"', "discard"),
    ])
    new = _tree([
        DecisionNode('priority == "high"', "escalate_urgent"),
        DecisionNode('security_score > 0.8', "human_review"),
        DecisionNode('priority == "low"', "route_low"),
    ], default="new_default")
    out = render_diff(diff_trees(old, new))
    assert '+ added    if (priority == "low") -> route_low' in out
    assert '- removed  if (priority == "spam") -> discard' in out
    assert "~ changed  if (security_score > 0.8): 'escalate_security' -> 'human_review'" in out
    assert "~ default  'route_default' -> 'new_default'" in out
    assert "= unchanged 1 node(s)" in out
