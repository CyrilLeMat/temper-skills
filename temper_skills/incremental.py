"""Incremental mode (§4.2): re-crystallize an existing tree after a change.

Start the loop from a previously-converged tree rather than a blank draft, target
the deltas a new constraint / source update requires, and emit a structural diff so
the change is reviewable in a PR. Without this, the tree becomes the unmaintained
legacy the tool exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .backends import Backend
from .distill import _node_key, distill
from .schemas import ProposedNode, ProposedTree
from .sources import Persona, Sources
from .tree import DecisionNode, DecisionTree


def _seed_from_tree(tree: DecisionTree) -> tuple[ProposedTree, dict[str, int]]:
    """A DecisionTree -> (ProposedTree seed, survival map carried forward)."""
    nodes = [
        ProposedNode(condition=n.condition, outcome=n.outcome, sources=list(n.sources),
                     gray_zone=n.gray_zone)
        for n in tree.nodes
    ]
    survival = {_node_key(n.condition): n.rounds_survived for n in tree.nodes}
    return ProposedTree(nodes=nodes, default_outcome=tree.default_outcome), survival


@dataclass
class TreeDiff:
    added: list[DecisionNode] = field(default_factory=list)
    removed: list[DecisionNode] = field(default_factory=list)
    changed: list[tuple[DecisionNode, DecisionNode]] = field(default_factory=list)  # (old, new)
    unchanged: list[DecisionNode] = field(default_factory=list)
    default_change: tuple[str, str] | None = None  # (old, new) if the default moved

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed or self.default_change)


def diff_trees(old: DecisionTree, new: DecisionTree) -> TreeDiff:
    """Structural diff, keyed on the branch condition."""
    old_by_key = {_node_key(n.condition): n for n in old.nodes}
    new_by_key = {_node_key(n.condition): n for n in new.nodes}
    diff = TreeDiff()
    for key, n in new_by_key.items():
        if key not in old_by_key:
            diff.added.append(n)
        elif old_by_key[key].outcome != n.outcome:
            diff.changed.append((old_by_key[key], n))
        else:
            diff.unchanged.append(n)
    for key, n in old_by_key.items():
        if key not in new_by_key:
            diff.removed.append(n)
    if old.default_outcome != new.default_outcome:
        diff.default_change = (old.default_outcome, new.default_outcome)
    return diff


def render_diff(diff: TreeDiff) -> str:
    lines: list[str] = []
    for n in diff.added:
        lines.append(f"+ added    if ({n.condition}) -> {n.outcome}")
    for n in diff.removed:
        lines.append(f"- removed  if ({n.condition}) -> {n.outcome}")
    for old, new in diff.changed:
        lines.append(f"~ changed  if ({new.condition}): {old.outcome!r} -> {new.outcome!r}")
    if diff.default_change:
        lines.append(f"~ default  {diff.default_change[0]!r} -> {diff.default_change[1]!r}")
    lines.append(f"= unchanged {len(diff.unchanged)} node(s)")
    return "\n".join(lines)


def recrystallize(
    prior: DecisionTree,
    sources: Sources,
    adversaries: list[Persona] | None = None,
    profile: str = "standard",
    backend: Backend | None = None,
    gate=None,
    fn_name: str | None = None,
) -> tuple[DecisionTree, TreeDiff]:
    """Re-run the loop from ``prior`` against (changed) ``sources``; return (new_tree, diff)."""
    seed, survival = _seed_from_tree(prior)
    new_tree = distill(
        sources,
        adversaries=adversaries,
        profile=profile,
        backend=backend,
        gate=gate,
        fn_name=fn_name or prior.fn_name,
        seed_tree=seed,
        seed_survival=survival,
    )
    return new_tree, diff_trees(prior, new_tree)
