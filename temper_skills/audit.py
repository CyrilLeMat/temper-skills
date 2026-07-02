"""Pre-flight fitness check: is this skill's logic worth freezing into a tree?

The loop discovers a bad fit the expensive way — dog_food thrashes for rounds because
``domain_expert`` always finds one more toxin while ``overengineering_critic`` wants the
list gone (README, H4). This decides it up front, before the loop runs: the gate a
SkillClaw-style mass-evolution pipeline needs, since it can't hand-pick which evolved
skills to crystallize.

Three axes are judged by one LLM turn; the fourth — schema closure — is computed
deterministically from the schema you'd draft anyway. The verdict itself is a pure
function of the four, so the audit is as reproducible and explainable as the tree it gates.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .backends import Backend, auto_backend
from .ingest import InferredFeature, InferredSchema, ingest_skill

Action = Literal["temper", "externalize_data", "build_normalizer", "delegate_prose", "decompose"]


class JudgeScores(BaseModel):
    decisiveness: int = Field(
        ge=0, le=10,
        description="Does the skill resolve to a finite set of outcomes (route/classify/"
        "verdict), or is it mostly open-ended generation? Pure generation scores low — "
        "there is no decision to freeze.",
    )
    combinatorics: int = Field(
        ge=0, le=10,
        description="Does the difficulty live in INTERACTIONS among bounded features "
        "(priority x tier x score), or is it a flat unbounded lookup (a forever-growing "
        "list)? A flat list scores low — the tree thrashes and never converges.",
    )
    stakes: int = Field(
        ge=0, le=10,
        description="Is the decision repeated, auditable, and stable enough that freezing "
        "pays off, or one-off / changing weekly? Low means freezing won't pay for itself.",
    )
    distinct_decisions: int = Field(
        default=1, ge=0,
        description="How many SEPARABLE decisions this skill contains: 1 if it's a single "
        "coherent decision, >=2 if it's a flow of several (classify, then escalate, then "
        "draft …). The three axes above describe the skill as a WHOLE.",
    )
    rationale: dict[str, str] = Field(
        default_factory=dict,
        description="One short line per axis, keyed 'decisiveness', 'combinatorics', 'stakes'.",
    )


class FitnessReport(BaseModel):
    fn_name: str
    verdict: Literal["temper", "caveats", "skip"]
    decisiveness: int
    combinatorics: int
    stakes: int
    distinct_decisions: int = 1  # >=2 → the verdict averages several decisions; decompose first
    schema_closure: float  # 0-1, computed from the schema shape — not judged
    open_features: list[str] = []  # free-text fields whose value space ISN'T bounded
    n_features: int = 0
    rationale: dict[str, str] = {}  # the model's one-line reason per judged axis
    recommended_action: Action = "temper"  # what to DO with the skill, not just whether it fits
    action_hint: str = ""
    reasons: list[str]
    caveats: list[str]


AUDIT_SYSTEM = (
    "You judge whether an agent skill's DECISION logic is worth compiling into a "
    "deterministic decision tree. You are NOT judging whether the skill is good or "
    "well-written — only whether its routing/verdict logic is worth freezing into code.\n\n"
    "Score three axes 0-10 and give one line of rationale for each:\n"
    "  decisiveness — does it resolve to a finite set of outcomes (route/classify/verdict), "
    "or is it mostly open-ended generation? Pure generation scores low: nothing to freeze.\n"
    "  combinatorics — does the difficulty live in INTERACTIONS among bounded features "
    "(e.g. priority x tier x score x flag), or is it a flat unbounded lookup (a "
    "forever-growing list of items)? A flat list scores low: the tree thrashes and never "
    "converges, because each round surfaces one more item.\n"
    "  stakes — is the decision repeated, auditable, and stable enough that freezing it "
    "pays off, or is it one-off / likely to change weekly? Low stakes score low.\n\n"
    "Also report distinct_decisions: how many SEPARABLE decisions the skill contains — 1 for "
    "a single coherent decision, >=2 for a flow of several (e.g. classify, then escalate, "
    "then draft a reply). Score the three axes for the skill as a WHOLE."
)


def _is_closed(f: InferredFeature) -> bool:
    """Does this feature pin to a BOUNDED value space?

    Numbers/bools are bounded enough to branch on. A string is bounded only if it's a
    genuine small enum — and an inferred schema can't *prove* that, so we credit it only
    on a strong signal ("one of …" or quoted alternatives). We deliberately DON'T treat a
    comma-listing description as an enum: a free-text identifier like ``food_item`` whose
    description happens to give examples ("chocolate, grapes, onion") is the unbounded tail,
    not a closed set. Crediting it was the false-100%-closure bug that let dog_food read as
    a clean fit.
    """
    if f.type != "string":
        return True
    d = (f.description or "").lower()
    return "one of" in d or (f.description or "").count('"') >= 4


def schema_closure(inferred: InferredSchema) -> float:
    """Fraction of features that pin to a bounded value space. A schema dominated by open
    free-text strings is the thrash failure mode wearing a schema."""
    feats = inferred.features
    if not feats:
        return 0.0
    return sum(1 for f in feats if _is_closed(f)) / len(feats)


def open_features(inferred: InferredSchema) -> list[str]:
    """Names of the free-text fields whose value space ISN'T bounded — where the
    determinism guarantee leaks into the normalizer you own (README, "What it is not")."""
    return [f.name for f in inferred.features if not _is_closed(f)]


# label · what to do · delegated tool (None = temper-skills does it)
ACTIONS: dict[str, tuple[str, str, str | None]] = {
    "temper": (
        "Freeze the decision into a tree",
        "run `temper-skills ingest` — the core path",
        None,
    ),
    "externalize_data": (
        "Externalize the list as data, don't grow a tree",
        "emit a versioned data file + an exact-match matcher; temper ONLY the residual "
        "interacting logic (e.g. a dose-by-weight rule)",
        None,
    ),
    "build_normalizer": (
        "Build the feature normalizer first",
        "the decision branches on free text ({fields}); pin those to canonical features "
        "(Instructor / your own extractor) before tempering",
        None,
    ),
    "delegate_prose": (
        "Improve it as prose — there's no decision to freeze",
        "refine wording / triggering / examples elsewhere",
        "skill-creator",
    ),
    "decompose": (
        "Split into per-decision trees first",
        "this skill is a flow of several decisions — run `temper-skills decompose`, temper "
        "each, and keep a thin orchestrator (the scores above average them)",
        None,
    ),
}


def recommend_action(j: JudgeScores, open_feats: list[str]) -> Action:
    """Route a skill to its next useful action — a pure function of the same axes the
    verdict uses. Cascade, most-disqualifying first (mirrors verdict_of)."""
    if j.distinct_decisions >= 2:
        return "decompose"                 # a flow of several decisions — split before tempering
    if j.decisiveness < 4:
        return "delegate_prose"            # generation skill — not our lane
    if open_feats:
        # the decision branches on un-pinned free text. How we fix it depends on whether
        # there's genuine interacting logic, or it's a flat list keyed on that text.
        return "externalize_data" if j.combinatorics <= 5 else "build_normalizer"
    return "temper"                        # decisive + closed schema → tree-shaped


def verdict_of(
    j: JudgeScores, closure: float, n_features: int
) -> tuple[Literal["temper", "caveats", "skip"], list[str], list[str]]:
    """Pure rubric: map scored axes to a verdict. The thresholds are the judgement call —
    they are pinned by test_audit so a change to them is a visible, reviewed diff."""
    reasons: list[str] = []
    caveats: list[str] = []

    if j.decisiveness < 4:
        reasons.append("no finite decision to freeze — mostly generation")
        return "skip", reasons, caveats
    if closure < 0.5 and j.combinatorics < 4:
        reasons.append(
            "flat free-text lookup, no interacting structure (H4) — the loop will thrash"
        )
        return "skip", reasons, caveats

    if closure < 0.7:
        caveats.append(
            f"schema only {closure:.0%} closed — the guarantee rests on YOUR normalizer"
        )
    if j.combinatorics <= 5:
        caveats.append(
            f"borderline combinatorics ({j.combinatorics}/10) — the hardness is partly a flat "
            "lookup, so the loop may thrash on an unbounded tail (H4)"
        )
    if n_features <= 1:
        caveats.append("single feature — confirm the tree isn't just a lookup table")
    if j.stakes < 4:
        caveats.append("low stakes / unstable — freezing may not pay for itself")

    reasons.append(
        f"decisive ({j.decisiveness}/10) with interacting structure ({j.combinatorics}/10)"
    )
    return ("caveats" if caveats else "temper"), reasons, caveats


def audit_skill(
    path: str,
    backend: Backend | None = None,
    model: str = "claude-sonnet-4-6",
    schema: InferredSchema | None = None,
) -> FitnessReport:
    """Assess a skill's temper-fitness. One LLM turn for the judged axes (plus one to
    infer the schema, if not supplied) — cheap enough to fan across a whole library."""
    backend = backend or auto_backend(model)
    if schema is None:
        schema = ingest_skill(path, schema=None, backend=backend, propose_schema_only=True)
    with open(path) as f:
        skill_text = f.read()

    j = backend.complete(
        AUDIT_SYSTEM, f"SKILL:\n{skill_text}\n\nScore the three axes.", JudgeScores
    )
    closure = schema_closure(schema)
    opens = open_features(schema)
    verdict, reasons, caveats = verdict_of(j, closure, len(schema.features))
    action = recommend_action(j, opens)
    if j.distinct_decisions >= 2:
        caveats.insert(0, f"~{j.distinct_decisions} distinct decisions — the scores above "
                       "AVERAGE them; decompose before trusting this verdict")
    _, hint, tool = ACTIONS[action]
    hint = hint.format(fields=", ".join(opens)) if "{fields}" in hint else hint
    if tool:
        hint = f"{hint} → {tool}"
    return FitnessReport(
        fn_name=schema.fn_name,
        verdict=verdict,
        decisiveness=j.decisiveness,
        combinatorics=j.combinatorics,
        stakes=j.stakes,
        distinct_decisions=j.distinct_decisions,
        schema_closure=closure,
        open_features=opens,
        n_features=len(schema.features),
        rationale=j.rationale,
        recommended_action=action,
        action_hint=hint,
        reasons=reasons,
        caveats=caveats,
    )
