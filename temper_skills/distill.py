"""The adversarial loop: propose → critique → arbitrate → repeat (§4.2)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from .backends import Backend, auto_backend
from .schemas import PersonaVerdict, ProposedTree, ProposerArbitration
from .sources import (
    BAD_FAITH_ACTOR,
    DOMAIN_EXPERT,
    EDGE_CASE_HUNTER,
    LITERALIST,
    OVERENGINEERING_CRITIC,
    Persona,
    Sources,
)
from .tree import DecisionNode, DecisionTree

PROFILES = {
    # name:        (max_rounds, stop_after_quiet_rounds, interactive, provenance)
    "quick": (8, 2, False, False),
    "standard": (20, 3, True, True),
    # audit-grade today = more rounds + stricter convergence (N=5) + the gate.
    # Tournament orchestration, required citations, and per-gray-zone sign-off
    # (the deeper audit-grade behaviors in the design doc) are roadmap, not built.
    "audit-grade": (50, 5, True, True),
}

# A round only counts toward convergence if every persona scores at least this
# high (the panel agrees the tree is solid) AND no new gray zone appeared.
SCORE_BAR = 8

# Default adversaries per profile (the overengineering_critic is always appended).
# More personas of one model share blind spots (H5) and add cost + convergence
# surface, so the cheap profiles run a lean, diverse panel and the full panel is
# reserved for audit-grade. Override with distill(adversaries=[...]).
PROFILE_PERSONAS: dict[str, list[Persona]] = {
    "quick": [EDGE_CASE_HUNTER],
    "standard": [EDGE_CASE_HUNTER, DOMAIN_EXPERT],
    "audit-grade": [LITERALIST, EDGE_CASE_HUNTER, BAD_FAITH_ACTOR, DOMAIN_EXPERT],
}


@dataclass
class RoundResult:
    round: int
    max_rounds: int
    verdicts: list[PersonaVerdict]
    arbitration: ProposerArbitration
    tree: ProposedTree
    survival: dict[str, int]  # condition -> rounds survived

    @property
    def min_score(self) -> int:
        return min((v.score for v in self.verdicts), default=0)

    @property
    def mean_score(self) -> float:
        return round(sum(v.score for v in self.verdicts) / len(self.verdicts), 1) if self.verdicts else 0.0


# A gate decides whether to continue after each round.
# Returns "continue", "stop" (export now), or "abort".
Gate = Callable[[RoundResult], str]


def _render_tree(tree: ProposedTree) -> str:
    lines = []
    for i, n in enumerate(tree.nodes, 1):
        gz = f"   [gray_zone: {n.gray_zone}]" if n.gray_zone else ""
        lines.append(f"  n{i}: if ({n.condition}) -> {n.outcome}{gz}")
    lines.append(f"  default -> {tree.default_outcome}")
    return "\n".join(lines)


def _sources_block(sources: Sources) -> str:
    parts = []
    if sources.skill_text:
        parts.append(
            "ORIGINAL SKILL (the prompt logic being migrated — extract its routing "
            f"logic, not its prose generation):\n{sources.skill_text}\n"
        )
    parts += [
        "SCHEMA (pre-computed structured features the tree may branch on):",
        json.dumps(sources.json_schema, indent=2),
    ]
    if sources.constraints:
        parts.append("\nCONSTRAINTS (hard ones are non-negotiable):")
        for i, c in enumerate(sources.constraints, 1):
            tag = " [HARD]" if c.get("hard") else ""
            parts.append(f"  constraints#{i}{tag}: {c['rule']}")
    if sources.examples:
        parts.append("\nEXAMPLES (ratified cases — waypoints, not a dataset):")
        for i, e in enumerate(sources.examples, 1):
            parts.append(f"  examples#{i}: input={e.get('input')} -> expected={e.get('expected')}")
    return "\n".join(parts)


PROPOSER_SYSTEM = (
    "You compile an LLM agent's decision logic into a deterministic decision tree. "
    "You output a flat, ordered list of branches (first match wins) over the schema's "
    "pre-computed features. You must never contradict a HARD constraint. Mobilize what "
    "you know about public guidelines in this domain to propose rules the user did not "
    "list, but keep the tree as simple as the domain truly requires — depth should "
    "reflect domain complexity, not loop richness. Conditions must be valid Python "
    "boolean expressions referencing feature names directly, and must be NONE-SAFE: any "
    "feature may be absent (None) at inference, so guard before comparing — "
    "`x is not None and x < 1`, never bare `x < 1`; coerce strings with "
    "`(s or '').strip().lower()`. A condition must never raise on a missing feature."
)

PERSONA_SYSTEM = (
    "You are one reviewer on a panel challenging a proposed decision tree, like a senior "
    "engineer reviewing an RFC. Attack ONLY from your assigned angle. Be concrete: when "
    "you find a flaw, give a specific feature assignment the tree mishandles. If the tree "
    "is sound from your angle, say so and score it high. This is decision-robustness "
    "review of business logic — not security scanning."
)


def _initial_tree(backend: Backend, sources: Sources) -> ProposedTree:
    user = (
        f"{_sources_block(sources)}\n\n"
        "Draft the initial decision tree. Cover the obvious cases first. Flag any "
        "ambiguous region as a gray_zone rather than guessing."
    )
    return backend.complete(PROPOSER_SYSTEM, user, ProposedTree)


def _critique(backend: Backend, sources: Sources, persona: Persona, tree: ProposedTree) -> PersonaVerdict:
    user = (
        f"Your angle ({persona.name}): {persona.style}\n\n"
        f"{_sources_block(sources)}\n\n"
        f"CURRENT TREE:\n{_render_tree(tree)}\n\n"
        f"Review the tree strictly from your angle. Set persona to '{persona.name}'."
    )
    return backend.complete(PERSONA_SYSTEM, user, PersonaVerdict)


def _arbitrate(
    backend: Backend, sources: Sources, tree: ProposedTree, verdicts: list[PersonaVerdict],
    incremental: bool = False,
) -> ProposerArbitration:
    crit = "\n".join(
        f"  {v.persona} (score {v.score}, {v.verdict}): {v.detail}"
        + (f" | case: {v.proposed_case}" if v.proposed_case else "")
        for v in verdicts
    )
    incr = (
        "INCREMENTAL RUN: the CURRENT TREE is an existing, previously-converged tree; a "
        "change to constraints/sources prompted this run. Preserve every node the change "
        "does NOT affect — keep its condition and outcome verbatim. Only add, modify, or "
        "remove nodes the new constraints/sources (or a surviving critique) require. "
        "Minimize churn.\n\n"
        if incremental else ""
    )
    user = (
        f"{incr}"
        f"{_sources_block(sources)}\n\n"
        f"CURRENT TREE:\n{_render_tree(tree)}\n\n"
        f"PERSONA VERDICTS:\n{crit}\n\n"
        "Arbitrate. For each persona, decide kept/changed/rejected with a one-line "
        "rationale. Then output the improved tree. Add a branch only if a critique "
        "justifies it AND a domain expert would write it by hand; collapse branches the "
        "overengineering_critic flags as unnecessary. Respect every HARD constraint. "
        "Give a convergence_estimate (0-100) for how settled the tree now is."
    )
    return backend.complete(PROPOSER_SYSTEM, user, ProposerArbitration)


def _node_key(condition: str) -> str:
    return " ".join(condition.split())


def distill(
    sources: Sources,
    adversaries: list[Persona] | None = None,
    profile: str = "standard",
    model: str = "claude-sonnet-4-6",
    backend: Backend | None = None,
    gate: Gate | None = None,
    fn_name: str = "decide",
    seed_tree: ProposedTree | None = None,
    seed_survival: dict[str, int] | None = None,
) -> DecisionTree:
    """Run the adversarial loop and return a deterministic DecisionTree.

    Pass ``seed_tree`` (with ``seed_survival``) to start from an existing tree
    instead of a blank draft — incremental mode (see incremental.recrystallize).
    """
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; choose from {list(PROFILES)}")
    max_rounds, stop_quiet, _interactive, provenance = PROFILES[profile]

    personas = list(adversaries) if adversaries is not None else list(PROFILE_PERSONAS[profile])
    # The overengineering_critic is always on (§5.5).
    if not any(p.name == OVERENGINEERING_CRITIC.name for p in personas):
        personas.append(OVERENGINEERING_CRITIC)

    backend = backend or auto_backend(model)
    incremental = seed_tree is not None
    if incremental:
        tree = seed_tree
        survival = dict(seed_survival or {_node_key(n.condition): 1 for n in tree.nodes})
    else:
        tree = _initial_tree(backend, sources)
        survival = {_node_key(n.condition): 1 for n in tree.nodes}
    seen_gray_zones: set[str] = {n.gray_zone for n in tree.nodes if n.gray_zone}
    stale_rounds = 0
    best_mean = -1.0
    last_arbitration: ProposerArbitration | None = None

    for r in range(1, max_rounds + 1):
        try:
            verdicts = [_critique(backend, sources, p, tree) for p in personas]
            arbitration = _arbitrate(backend, sources, tree, verdicts, incremental=incremental)
        except Exception:
            # A transient backend failure shouldn't throw away the rounds already
            # paid for. With nothing to salvage (round 1), re-raise; otherwise keep
            # the last good tree and finalize it.
            if last_arbitration is None:
                raise
            break
        new_tree = arbitration.tree
        last_arbitration = arbitration

        new_keys = {_node_key(n.condition) for n in new_tree.nodes}
        for key in new_keys:
            survival[key] = survival.get(key, 0) + 1

        new_gray = {n.gray_zone for n in new_tree.nodes if n.gray_zone} - seen_gray_zones
        seen_gray_zones |= new_gray

        tree = new_tree
        result = RoundResult(r, max_rounds, verdicts, arbitration, tree, dict(survival))

        # Convergence = the scores *stabilize* (the plan's actual criterion), not an
        # absolute bar that may never be reached. A round makes progress if the mean
        # score improved or a new gray zone surfaced; once neither happens for
        # `stop_quiet` rounds the loop has plateaued — stop, whether the plateau is
        # high (good tree) or low (the loop can't do better on this schema).
        progressed = result.mean_score > best_mean + 0.1 or bool(new_gray)
        best_mean = max(best_mean, result.mean_score)
        stale_rounds = 0 if progressed else stale_rounds + 1

        decision = gate(result) if gate else "continue"
        if decision == "abort":
            raise KeyboardInterrupt("distillation aborted by gate")
        if decision == "stop":
            break
        if stale_rounds >= stop_quiet:
            break

    model_tag = f"{backend.model} via {backend.name}"
    final = _finalize(tree, last_arbitration, survival, sources, model_tag, profile, provenance, fn_name)
    # The ratified examples are the loop's own correctness signal: check the
    # converged tree against them and surface any disagreement (§4.1 / §4.5).
    if sources.examples:
        final.example_report = _check_examples(final, sources.examples)
    return final


def _check_examples(tree: DecisionTree, examples: list[dict]):
    from .validate import fn_from_tree, label_match, run_validation

    dataset = [{"input": e["input"], "expected": e["expected"]} for e in examples]
    return run_validation(fn_from_tree(tree), dataset, label_match)


def _finalize(
    tree: ProposedTree,
    arbitration: ProposerArbitration | None,
    survival: dict[str, int],
    sources: Sources,
    model: str,
    profile: str,
    provenance: bool,
    fn_name: str,
) -> DecisionTree:
    critic_notes = {}
    if arbitration:
        for e in arbitration.entries:
            if e.persona == OVERENGINEERING_CRITIC.name and e.decision != "rejected":
                critic_notes["_global"] = f"{e.decision} — {e.rationale}"
    nodes = [
        DecisionNode(
            condition=n.condition,
            outcome=n.outcome,
            rounds_survived=survival.get(_node_key(n.condition), 1),
            sources=n.sources,
            gray_zone=n.gray_zone,
        )
        for n in tree.nodes
    ]
    if nodes and "_global" in critic_notes:
        nodes[0].critic_note = critic_notes["_global"]
    return DecisionTree(
        nodes=nodes,
        default_outcome=tree.default_outcome,
        features=sources.feature_names,
        fn_name=fn_name,
        model=model,
        profile=profile,
        include_provenance=provenance,
    )
