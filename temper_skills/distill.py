"""The adversarial loop: propose → critique → arbitrate → repeat (§4.2)."""

from __future__ import annotations

import copy
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from .backends import Backend, auto_backend
from .schemas import (
    PersonaVerdict,
    ProposedExampleSet,
    ProposedTree,
    ProposerArbitration,
)
from .sources import (
    BAD_FAITH_ACTOR,
    DOMAIN_EXPERT,
    EDGE_CASE_HUNTER,
    LITERALIST,
    OUTCOME_CRITIC,
    OVERENGINEERING_CRITIC,
    SCHEMA_CRITIC,
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

# Default adversaries per profile (the overengineering_critic is always appended).
# More personas of one model share blind spots (H5) and add cost + convergence
# surface, so the cheap profiles run a lean, diverse panel and the full panel is
# reserved for audit-grade. Override with distill(adversaries=[...]).
# The schema_critic and its output-side dual the outcome_critic join the gating profiles
# (standard, audit-grade), where widening the schema/outcome set is possible; quick stays lean.
# The overengineering_critic is appended to every panel below.
PROFILE_PERSONAS: dict[str, list[Persona]] = {
    "quick": [EDGE_CASE_HUNTER],
    "standard": [EDGE_CASE_HUNTER, DOMAIN_EXPERT, SCHEMA_CRITIC, OUTCOME_CRITIC],
    "audit-grade": [LITERALIST, EDGE_CASE_HUNTER, BAD_FAITH_ACTOR, DOMAIN_EXPERT,
                    SCHEMA_CRITIC, OUTCOME_CRITIC],
}


# Co-evolving schema: a feature the schema_critic adds must EARN a surviving branch within
# this many rounds, else it is reverted (fitness = the proposer actually branches on it). This
# bounds schema growth by tree size so the loop still converges (§ the "earn-a-branch" guard).
_EARN_ROUNDS = 2

_JSON_TYPE = {"float": "number", "int": "integer", "bool": "boolean", "str": "string"}


def _parse_feature_spec(spec: str) -> tuple[str, dict]:
    """Parse a schema_critic 'name: type — why' into (name, json-schema-fragment).

    Best-effort: unknown/compound types (Literal[...], a|b) fall back to string. Returns
    ("", {}) if the spec has no parseable name."""
    head = spec.split("—", 1)[0].split(" - ", 1)[0].strip()
    name, _, type_part = head.partition(":")
    name = name.strip()
    if not name or not name.isidentifier():
        return "", {}
    t = type_part.strip().lower()
    frag = {"type": _JSON_TYPE.get(t, "string")}
    return name, frag


def _feature_used_in_tree(name: str, tree: ProposedTree) -> bool:
    """Does any node condition branch on this feature (word-boundary match)?"""
    pat = re.compile(rf"\b{re.escape(name)}\b")
    return any(pat.search(n.condition or "") for n in tree.nodes)


@dataclass
class RoundResult:
    round: int
    max_rounds: int
    verdicts: list[PersonaVerdict]
    arbitration: ProposerArbitration
    tree: ProposedTree
    survival: dict[str, int]  # condition -> rounds survived
    agreement: float | None = None  # ratified-example agreement, if examples were given
    proposed_count: int = 0  # proposed validation cases accumulated so far
    proposed_passed: int = 0  # of those, how many the current tree satisfies
    ratified_count: int = 0  # ratified examples supplied as input

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

EXAMPLE_PROPOSER_SYSTEM = (
    "You draft discriminating test cases for the cells a decision tree leaves contested "
    "or unproven — the inputs a human reviewer should rule on to pin the tree down. Each "
    "label you give is a PROPOSAL awaiting human ratification, not ground truth: you are "
    "extending a validation set, not grading your own work. Target gray zones and "
    "boundary cells; never duplicate an existing ratified example."
)

ARBITER_SYSTEM = (
    "You are an INDEPENDENT arbiter — NOT the author of this tree. A separate proposer "
    "drafted the branches and an adversarial panel critiqued them; you rule on each "
    "finding (kept / changed / rejected) on its merits, owing the proposer no deference: "
    "keep a branch because the logic and the source justify it, not because it is already "
    "there. Add a branch only if a critique justifies it AND a domain expert would write "
    "it by hand; collapse a branch the overengineering_critic flags ONLY when doing so "
    "changes no outcome. Never contradict a HARD constraint. Same code rules as the "
    "proposer: conditions are valid, NONE-safe Python boolean expressions over the feature "
    "names (guard before comparing — `x is not None and x < 1`; coerce strings with "
    "`(s or '').strip().lower()`)."
)


def _initial_tree(backend: Backend, sources: Sources) -> ProposedTree:
    user = (
        f"{_sources_block(sources)}\n\n"
        "Draft the initial decision tree. Cover the obvious cases first. Flag any "
        "ambiguous region as a gray_zone rather than guessing."
    )
    return backend.complete(PROPOSER_SYSTEM, user, ProposedTree)


def _critique(backend: Backend, sources: Sources, persona: Persona, tree: ProposedTree,
              closed: list[str] | None = None) -> PersonaVerdict:
    if persona.name == SCHEMA_CRITIC.name:
        tests_clause = (
            "Leave `proposed_tests` EMPTY. Your job is the schema's EXPRESSIVENESS: judge "
            "whether the source implies a feature the schema cannot express (so the tree is "
            "forced to punt or over-approximate). If so, set verdict='schema_too_thin' and "
            "list each gap in `proposed_features` as 'name: type — why the source needs it'. "
            "If the schema can express everything the source decides on, score high and say so."
        )
    elif persona.name == OUTCOME_CRITIC.name:
        tests_clause = (
            "Leave `proposed_tests` EMPTY. Your job is the OUTCOME set's expressiveness: judge "
            "whether the source implies a distinct answer the current outcomes cannot express, "
            "so two genuinely different correct answers are forced to collapse into one label "
            "(or a case is routed to an outcome that is only approximately right). If so, set "
            "verdict='outcome_too_coarse' and list each missing outcome in `proposed_outcomes` "
            "as 'outcome — why (which two cases collapse today)'. If the outcome set can express "
            "every answer the source calls for, score high and say so."
        )
    elif persona.name == OVERENGINEERING_CRITIC.name:
        tests_clause = (
            "Leave `proposed_tests` EMPTY — your job is to remove unjustified complexity, "
            "not to add test cases."
        )
    else:
        tests_clause = (
            "Whenever you find a flaw, ALSO populate `proposed_tests`: one or more concrete "
            "cases, each a full `input` (a feature assignment over the schema features), the "
            "`expected` outcome you believe is correct, and a one-line `rationale`. These "
            "extend a human-ratified validation set — give your best-judgment label; a human "
            "ratifies it, it is not trusted blindly. Use exact schema feature names and values."
        )
    # Settled trade-offs the proposer has already ruled on. Without this, a persona re-raises
    # the same rejected point every round and pins its own score low forever — so the panel
    # never climbs even on a tree that's as good as it will get.
    closed_clause = ""
    if closed:
        closed_clause = (
            "\n\nSETTLED — the proposer has deliberately accepted these as gray zones or "
            "rejected a prior critique about them. Do NOT re-raise them or lower your score "
            "for them; they are decided. Score only on NEW issues:\n"
            + "\n".join(f"  - {c}" for c in closed)
        )
    user = (
        f"Your angle ({persona.name}): {persona.style}\n\n"
        f"{_sources_block(sources)}\n\n"
        f"CURRENT TREE:\n{_render_tree(tree)}\n\n"
        f"Review the tree strictly from your angle. Set persona to '{persona.name}'.\n\n"
        f"{tests_clause}{closed_clause}"
    )
    return backend.complete(PERSONA_SYSTEM, user, PersonaVerdict)


def _critique_all(
    backend: Backend, sources: Sources, personas: list[Persona], tree: ProposedTree,
    closed: list[str] | None = None,
) -> list[PersonaVerdict]:
    """Run every persona's critique of the SAME tree concurrently (they're independent).

    Order-preserving (executor.map), so the panel and tests stay deterministic. This is
    the bulk of a round, so parallelizing it cuts round latency roughly N×.
    """
    if len(personas) <= 1:
        return [_critique(backend, sources, p, tree, closed) for p in personas]
    with ThreadPoolExecutor(max_workers=len(personas)) as ex:
        return list(ex.map(lambda p: _critique(backend, sources, p, tree, closed), personas))


def _arbitrate(
    backend: Backend, sources: Sources, tree: ProposedTree, verdicts: list[PersonaVerdict],
    incremental: bool = False, regressed_last: bool = False,
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
    caution = (
        "NOTE: your previous revision REGRESSED (it lowered the validation pass-rate or "
        "broke a ratified example) and was DISCARDED — the CURRENT TREE below is the best "
        "version so far. Revise it only if you can RAISE the pass-rate, or remove/merge a "
        "node WITHOUT dropping any case. Do not collapse or reorder branches when that "
        "loses coverage; if no safe improvement exists, return the tree unchanged.\n\n"
        if regressed_last else ""
    )
    user = (
        f"{incr}{caution}"
        f"{_sources_block(sources)}\n\n"
        f"CURRENT TREE:\n{_render_tree(tree)}\n\n"
        f"PERSONA VERDICTS:\n{crit}\n\n"
        "Arbitrate. For each persona, decide kept/changed/rejected with a one-line "
        "rationale. Then output the improved tree. Add a branch only if a critique "
        "justifies it AND a domain expert would write it by hand; collapse branches the "
        "overengineering_critic flags as unnecessary ONLY when doing so changes no outcome. "
        "Respect every HARD constraint. "
        "Give a convergence_estimate (0-100) for how settled the tree now is."
    )
    # The arbiter runs under its OWN system prompt, not PROPOSER_SYSTEM: the agent that
    # rules kept/changed/rejected must not be the one defending its own draft (§4.2).
    return backend.complete(ARBITER_SYSTEM, user, ProposerArbitration)


def _node_key(condition: str) -> str:
    return " ".join(condition.split())


def _condition_ok(condition: str) -> bool:
    try:
        compile(f"({condition})", "<cond>", "eval")
        return True
    except SyntaxError:
        return False


def _sanitize(tree: ProposedTree) -> ProposedTree:
    """Drop nodes whose condition won't compile so a malformed branch from the model can
    never reach scoring or the exported file — a condition that can't compile can't run,
    and dropping it is strictly safer than shipping a SyntaxError."""
    good = [n for n in tree.nodes if _condition_ok(n.condition)]
    if len(good) == len(tree.nodes):
        return tree
    return ProposedTree(nodes=good, default_outcome=tree.default_outcome)


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
    propose_examples: bool = True,
    evolve_schema: bool = True,
    checkpoint: "Callable[[DecisionTree], None] | None" = None,
) -> DecisionTree:
    """Run the adversarial loop and return a deterministic DecisionTree.

    Pass ``seed_tree`` (with ``seed_survival``) to start from an existing tree
    instead of a blank draft — incremental mode (see incremental.recrystallize).

    ``propose_examples`` (on by default) builds a validation set as the loop runs: every
    persona except the overengineering_critic contributes discriminating cases each round.
    The loop SCORES the tree against these (adversary-authored) cases to pick the best
    tree and to decide convergence — so it returns a good final result without waiting on
    human ratification. Ratified examples, when supplied, rank ahead of the proposed ones
    and are never traded away. The proposed set is attached as ``tree.proposed_examples``
    for the user to ratify and harden later; set ``propose_examples=False`` to skip it.

    ``checkpoint`` (if given) is called with the current finalized tree after every round,
    so a caller can persist progress — you can follow the tree as it evolves and a late
    crash never throws away the rounds already paid for.
    """
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; choose from {list(PROFILES)}")
    max_rounds, stop_quiet, _interactive, provenance = PROFILES[profile]

    # Co-evolving schema: mutate a private copy so the caller's Sources is never touched.
    if evolve_schema:
        sources = copy.copy(sources)
        sources.json_schema = copy.deepcopy(sources.json_schema)
        sources.json_schema.setdefault("properties", {})

    personas = list(adversaries) if adversaries is not None else list(PROFILE_PERSONAS[profile])
    # The overengineering_critic is always on (§5.5).
    if not any(p.name == OVERENGINEERING_CRITIC.name for p in personas):
        personas.append(OVERENGINEERING_CRITIC)

    backend = backend or auto_backend(model)
    model_tag = f"{backend.model} via {backend.name}"
    incremental = seed_tree is not None
    if incremental:
        tree = seed_tree
        survival = dict(seed_survival or {_node_key(n.condition): 1 for n in tree.nodes})
    else:
        tree = _sanitize(_initial_tree(backend, sources))
        survival = {_node_key(n.condition): 1 for n in tree.nodes}
    stale_rounds = 0
    regressed_last = False
    last_arbitration: ProposerArbitration | None = None

    # The proposed validation set grows as the loop runs: every persona (except the
    # overengineering_critic) contributes discriminating cases each round, deduped here
    # by input and against any ratified examples. Zero extra LLM calls — these ride
    # along in the critiques the personas already return.
    proposed: dict[str, dict] = {}
    existing_inputs = {_canon(e["input"]) for e in sources.examples}
    # Advisory expressiveness findings, deduped across rounds. Outcomes are free-form in the
    # library (no ceiling), so the outcome_critic stays advisory here. Schema features co-evolve:
    #   watching[name] = (round_added, spec)  — added, on probation until it earns a branch
    #   earned[name]   = spec                 — branched on; now a permanent schema member
    #   schema_gaps    = specs proposed but reverted (earned no branch in _EARN_ROUNDS)
    schema_gaps: dict[str, None] = {}
    outcome_gaps: dict[str, None] = {}
    watching: dict[str, tuple[int, str]] = {}
    earned: dict[str, str] = {}

    # We SCORE the tree against those proposed cases, not just the ratified ones: the
    # point of the tool is to hand back a good final tree without waiting on a human to
    # ratify every step. The labels are written by the ADVERSARIAL personas, not the
    # proposer, so this is "satisfy your critics", not "grade your own homework".
    # Ranking is lexicographic — (ratified pass-rate, proposed pass-rate, persona score) —
    # so ratified ground truth, when present, always wins and is never traded away to
    # match a proposed label. `candidates` keeps each round's tree; the winner is chosen
    # by re-scoring them all against the FINAL proposed set (fair: one denominator).
    # `stop_key` is the running plateau tracker.
    candidates: list[tuple[ProposedTree, ProposerArbitration | None, float]] = [(tree, None, -1.0)]
    stop_key = (_agreement(tree, sources, fn_name) or 1.0, -1.0, -1.0)

    for r in range(1, max_rounds + 1):
        # Feed the panel the proposer's settled trade-offs (the working tree's gray zones +
        # last round's rejected critiques) so a persona stops re-scoring a decided point down.
        closed = [n.gray_zone for n in tree.nodes if n.gray_zone]
        if last_arbitration:
            closed += [f"{e.persona}: {e.rationale}" for e in last_arbitration.entries
                       if e.decision == "rejected"]
        try:
            verdicts = _critique_all(backend, sources, personas, tree, closed)
            for v in verdicts:
                for oc in v.proposed_outcomes:
                    outcome_gaps.setdefault(oc, None)
                for feat in v.proposed_features:
                    if evolve_schema:
                        # Grow the schema: add the feature so THIS round's arbiter (and the
                        # next proposer) can branch on it. It's on probation until it earns a
                        # branch (below); if it never does, it's reverted, not shipped.
                        name, frag = _parse_feature_spec(feat)
                        if name and name not in sources.json_schema["properties"] \
                                and name not in earned:
                            sources.json_schema["properties"][name] = frag
                            watching.setdefault(name, (r, feat))
                    else:
                        schema_gaps.setdefault(feat, None)  # advisory-only (legacy behavior)
            if propose_examples:
                _harvest_proposed(verdicts, r, proposed, existing_inputs)
            arbitration = _arbitrate(backend, sources, tree, verdicts,
                                     incremental=incremental, regressed_last=regressed_last)
        except Exception:
            # A transient backend failure shouldn't throw away the rounds already
            # paid for. With nothing to salvage (round 1), re-raise; otherwise keep
            # the best tree so far and finalize it.
            if last_arbitration is None:
                raise
            break
        new_tree = _sanitize(arbitration.tree)
        last_arbitration = arbitration

        # Earn-a-branch-or-revert: a probationary feature that the tree now branches on is
        # earned (permanent); one that hasn't earned a branch within _EARN_ROUNDS is reverted
        # out of the schema and recorded as an advisory gap. Keeps schema size ≤ tree size.
        if evolve_schema and watching:
            for name in list(watching):
                added_round, spec = watching[name]
                if _feature_used_in_tree(name, new_tree):
                    earned[name] = spec
                    del watching[name]
                elif r - added_round >= _EARN_ROUNDS:
                    sources.json_schema["properties"].pop(name, None)
                    schema_gaps.setdefault(spec, None)
                    del watching[name]

        for key in {_node_key(n.condition) for n in new_tree.nodes}:
            survival[key] = survival.get(key, 0) + 1

        # Score this round's ATTEMPT against the ratified examples (authoritative) and the
        # proposed cases (the panel's adversarial expectations).
        agreement = _agreement(new_tree, sources, fn_name)
        prop_items = list(proposed.values())
        prop_passed = _score(new_tree, prop_items, sources.feature_names, fn_name)
        result = RoundResult(r, max_rounds, verdicts, arbitration, new_tree, dict(survival),
                             agreement, proposed_count=len(prop_items),
                             proposed_passed=prop_passed,
                             ratified_count=len(sources.examples))
        candidates.append((new_tree, arbitration, result.mean_score))

        # Hill-climb: adopt the attempt as the working tree ONLY if it is not worse than the
        # current one. A regressing round is discarded and the NEXT round re-attempts from
        # the best tree (with a caution to the proposer) — so one bad collapse can't poison
        # the rest of the run. The final export still picks the best candidate across rounds.
        new_q = (agreement if agreement is not None else 1.0,
                 prop_passed / len(prop_items) if prop_items else 0.0,
                 -len(new_tree.nodes))
        if new_q >= _quality(tree, sources, prop_items, fn_name):
            tree = new_tree
            regressed_last = False
        else:
            regressed_last = True

        if checkpoint:  # persist the current best (working) tree — followable + crash-safe
            checkpoint(_finalize(tree, last_arbitration, survival, sources, model_tag,
                                 profile, provenance, fn_name))

        # Convergence: once no round beats the best for `stop_quiet` rounds, the loop has
        # plateaued — stop, whether the plateau is high (a good tree) or low (can't improve).
        round_key = (agreement if agreement is not None else 1.0,
                     prop_passed / len(prop_items) if prop_items else 0.0,
                     result.mean_score)
        if round_key > stop_key:
            stop_key = round_key
            stale_rounds = 0
        else:
            stale_rounds += 1

        decision = gate(result) if gate else "continue"
        if decision == "abort":
            raise KeyboardInterrupt("distillation aborted by gate")
        if decision == "stop":
            break
        if stale_rounds >= stop_quiet:
            break

    # Pick the tree to ship by re-scoring every candidate against the FINAL proposed set
    # (+ ratified), so a later round isn't judged on a smaller set than an earlier one.
    # `survival` is cumulative and keyed by condition, so it gives the right
    # rounds_survived for whichever tree wins.
    best_tree, best_arbitration = _select_best(candidates, sources, list(proposed.values()), fn_name)
    arb_for_final = best_arbitration if best_arbitration is not None else last_arbitration

    # Final earn-a-branch reconciliation against the WINNING tree: a co-evolution-added feature
    # ships only if the shipped tree actually branches on it; the rest revert to advisory gaps.
    # (Original, user-supplied schema features are never reverted — they're the naive seed.)
    added_features: list[str] = []
    if evolve_schema:
        for name in list(earned) + list(watching):
            spec = earned.get(name) or watching[name][1]
            if _feature_used_in_tree(name, best_tree):
                added_features.append(spec)
            else:
                sources.json_schema["properties"].pop(name, None)
                schema_gaps.setdefault(spec, None)

    final = _finalize(best_tree, arb_for_final, survival, sources, model_tag, profile, provenance, fn_name)
    if added_features:
        final.added_features = added_features  # the loop grew the schema by these (review them)
    if schema_gaps:
        final.schema_gaps = list(schema_gaps)  # advisory: prompt to re-open the schema gate
    if outcome_gaps:
        final.outcome_gaps = list(outcome_gaps)  # advisory: prompt to widen the outcome set
    _assert_compiles(final)  # never hand back a tree that doesn't import
    # The ratified examples are the loop's own correctness signal: check the
    # converged tree against them and surface any disagreement (§4.1 / §4.5).
    if sources.examples:
        final.example_report = _check_examples(final, sources.examples)
    # Attach the validation set the personas drafted as the loop ran, for a human to
    # ratify (§4.5). If the panel happened to propose nothing, fall back to one targeted
    # generation call over the gray zones so we never finalize without a proposed set.
    if propose_examples:
        items = list(proposed.values())
        if not items:
            items = [i for i in _propose_examples(backend, sources, final, fn_name)
                     if _canon(i["input"]) not in existing_inputs]
        final.proposed_examples = _stamp_proposed(final, items)
    return final


def _check_examples(tree: DecisionTree, examples: list[dict]):
    from .validate import fn_from_tree, label_match, run_validation

    dataset = [{"input": e["input"], "expected": e["expected"]} for e in examples]
    return run_validation(fn_from_tree(tree), dataset, label_match)


def _canon(inp: dict) -> str:
    return json.dumps(inp, sort_keys=True, default=str)


def _harvest_proposed(
    verdicts: list[PersonaVerdict], rnd: int, acc: dict[str, dict], existing_inputs: set[str]
) -> None:
    """Collect each non-critic persona's drafted test cases into ``acc`` (deduped).

    The cases ride along in the verdicts the personas already return, so this is free.
    The two counterweights are skipped — they restructure, they don't add cases."""
    for v in verdicts:
        if v.persona in (OVERENGINEERING_CRITIC.name, SCHEMA_CRITIC.name, OUTCOME_CRITIC.name):
            continue
        for ex in v.proposed_tests:
            if not ex.input:
                continue
            key = _canon(ex.input)
            if key in existing_inputs or key in acc:
                continue
            acc[key] = {
                "input": ex.input,
                "expected": ex.expected,
                "rationale": ex.rationale,
                "source": f"{v.persona} (round {rnd})",
            }


def _stamp_proposed(tree: DecisionTree, items: list[dict]) -> list[dict]:
    """Add the frozen tree's own prediction + the un-ratified status to each case.

    The prediction is computed here, deterministically — a machine-authored label never
    masquerades as ground truth, and a case whose proposed label differs from the tree's
    output is the highest-value one for a human to rule on."""
    from .validate import fn_from_tree

    fn = fn_from_tree(tree)
    out: list[dict] = []
    for it in items:
        try:
            prediction = fn(it["input"])
        except Exception as e:  # a case that crashes the tree is itself worth surfacing
            prediction = f"ERROR: {type(e).__name__}: {e}"
        out.append({**it, "tree_prediction": prediction, "status": "proposed"})
    return out


def _propose_examples(
    backend: Backend, sources: Sources, tree: DecisionTree, fn_name: str
) -> list[dict]:
    """Fallback generator: ask the model for cases targeting the gray zones directly.

    Only used when the persona panel happened to propose nothing, so the run never
    finalizes without a proposed set. Returns raw {input, expected, rationale} items;
    the caller dedups and stamps them."""
    gray = [n.gray_zone for n in tree.nodes if n.gray_zone]
    gray_block = "\n".join(f"  - {g}" for g in gray) or "  (none explicitly flagged)"
    user = (
        f"{_sources_block(sources)}\n\n"
        f"FROZEN TREE (the decision is now exactly this):\n{tree.to_source()}\n\n"
        f"GRAY ZONES still unresolved:\n{gray_block}\n\n"
        "Propose a small set of discriminating test cases (at most one or two per gray "
        "zone) that pin down these contested cells — the inputs a human reviewer should "
        "rule on. Give the outcome you believe is correct for each, as a PROPOSAL to be "
        "ratified. Do not duplicate any EXAMPLES already listed."
    )
    proposed = backend.complete(EXAMPLE_PROPOSER_SYSTEM, user, ProposedExampleSet)
    return [{"input": ex.input, "expected": ex.expected, "rationale": ex.rationale}
            for ex in proposed.examples]


def _score(tree: ProposedTree, items: list[dict], features: list[str], fn_name: str) -> int:
    """How many of ``items`` (validation cases) the current tree satisfies (label match).

    The proposed cases are the gaps personas found, so this pass-rate rising round over
    round is the loop visibly closing them — the per-iteration validation score."""
    if not items:
        return 0
    from .validate import fn_from_tree, label_match

    dt = DecisionTree(
        nodes=[DecisionNode(condition=n.condition, outcome=n.outcome) for n in tree.nodes],
        default_outcome=tree.default_outcome, features=features, fn_name=fn_name,
    )
    fn = fn_from_tree(dt)
    passed = 0
    for it in items:
        try:
            pred = fn(it["input"])
        except Exception as e:
            pred = f"ERROR: {type(e).__name__}: {e}"
        if label_match(pred, it["expected"]):
            passed += 1
    return passed


def _assert_compiles(tree: DecisionTree) -> None:
    """Belt-and-suspenders: refuse to return a tree whose source won't import."""
    from .validate import fn_from_tree
    try:
        fn_from_tree(tree)
    except SyntaxError as e:
        raise RuntimeError(f"refusing to export a tree that does not compile: {e}") from e


def _select_best(
    candidates: list[tuple[ProposedTree, "ProposerArbitration | None", float]],
    sources: Sources, prop_items: list[dict], fn_name: str,
) -> tuple[ProposedTree, "ProposerArbitration | None"]:
    """Pick the candidate tree with the best (ratified rate, proposed rate, persona score).

    Re-scores every candidate against the SAME final proposed set, so a round isn't
    flattered or penalised by how many cases existed when it ran. Ratified ground truth
    is the lexicographic primary — never traded away to match an adversary-proposed label."""
    best = (candidates[0][0], candidates[0][1])
    best_key = (-1.0, -1.0, -1.0)
    for tree, arb, mean in candidates:
        rat = _agreement(tree, sources, fn_name)
        key = (
            rat if rat is not None else 1.0,
            _score(tree, prop_items, sources.feature_names, fn_name) / len(prop_items)
            if prop_items else 0.0,
            mean,
        )
        if key > best_key:
            best_key = key
            best = (tree, arb)
    return best


def _quality(tree: ProposedTree, sources: Sources, prop_items: list[dict], fn_name: str):
    """Rank a tree: (ratified pass-rate, proposed pass-rate, fewer nodes). Higher is better.

    Ratified ground truth dominates; then how many adversary-proposed cases it passes; then,
    at equal correctness, the simpler tree wins — so a node merge that changes no outcome is
    an improvement, but a collapse that drops a case is not."""
    rat = _agreement(tree, sources, fn_name)
    prop_rate = (_score(tree, prop_items, sources.feature_names, fn_name) / len(prop_items)
                 if prop_items else 0.0)
    return (rat if rat is not None else 1.0, prop_rate, -len(tree.nodes))


def _agreement(tree: ProposedTree, sources: Sources, fn_name: str) -> float | None:
    """Ratified-example agreement for an in-flight ProposedTree (zero LLM — pure Python).

    The loop's own correctness signal each round: used both to keep the best tree and
    to catch a buzzer-beating regression where a late round breaks a ratified example.
    Returns None when there are no examples to score against.
    """
    if not sources.examples:
        return None
    dt = DecisionTree(
        nodes=[DecisionNode(condition=n.condition, outcome=n.outcome) for n in tree.nodes],
        default_outcome=tree.default_outcome,
        features=sources.feature_names,
        fn_name=fn_name,
    )
    return _check_examples(dt, sources.examples).agreement_rate


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
