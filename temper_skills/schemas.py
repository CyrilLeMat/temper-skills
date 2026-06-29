"""Pydantic schemas that force the loop's LLM calls into machine-parseable JSON.

A flat node list (not a nested tree) is used deliberately: structured outputs do
not support recursive schemas, and a flat if-ladder is what keeps the exported
function readable (§5.5 complexity contract).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProposedNode(BaseModel):
    condition: str = Field(
        description="A Python boolean expression over the schema's feature names, "
        'e.g. food_item == "chocolate" or (food_item == "peanut butter" and '
        'food_form == "low_fat"). Evaluated top to bottom; first match wins.'
    )
    outcome: str = Field(description="The categorical decision returned when the condition holds.")
    sources: list[str] = Field(
        default_factory=list,
        description="Where this rule came from: constraints#N, examples#N, or a "
        "public-knowledge tag like ASPCA or domain_expert.",
    )
    gray_zone: str | None = Field(
        default=None,
        description="An unresolved ambiguity near this node, or null if none.",
    )


class ProposedTree(BaseModel):
    nodes: list[ProposedNode] = Field(description="Ordered branches; first match wins.")
    default_outcome: str = Field(description="The fallthrough decision when no branch matches.")


class PersonaVerdict(BaseModel):
    persona: str
    score: int = Field(ge=0, le=10, description="0 = the tree fails this persona's lens; 10 = solid.")
    verdict: Literal["ok", "missing_case", "collapsible", "contradiction"]
    detail: str = Field(description="One sentence: what is wrong, or why it is fine.")
    proposed_case: str | None = Field(
        default=None,
        description="A concrete feature assignment the tree mishandles (as a short "
        "description or JSON-ish string), if verdict != ok.",
    )


class ArbitrationEntry(BaseModel):
    persona: str
    decision: Literal["kept", "changed", "rejected"]
    rationale: str = Field(description="One line explaining how the proposer resolved this critique.")


class ProposerArbitration(BaseModel):
    """The structured arbitrage log (§5.5) plus the next iteration of the tree."""

    entries: list[ArbitrationEntry]
    convergence_estimate: int = Field(
        ge=0, le=100, description="Rough percent: how settled is the tree (0–100)."
    )
    tree: ProposedTree


class ProposedExample(BaseModel):
    """A discriminating test case the loop drafts for a contested/uncovered cell.

    The label is a PROPOSAL for a human to ratify, never ground truth — the loop
    must not grade its own homework (see distill._propose_examples)."""

    input: dict = Field(
        description="A concrete feature assignment (feature_name -> value) targeting a "
        "gray zone or a cell no ratified example covers. Use only schema feature names."
    )
    expected: str = Field(
        description="The outcome you believe is correct for this input — a PROPOSAL to be "
        "ratified by a human reviewer, not asserted ground truth."
    )
    rationale: str = Field(
        description="Why this case discriminates: which gray zone or contested cell it pins down."
    )


class ProposedExampleSet(BaseModel):
    examples: list[ProposedExample] = Field(default_factory=list)
