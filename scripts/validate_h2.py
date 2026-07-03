"""Phase 0 go/no-go: does the adversarial loop surface the xylitol edge case
UNPROMPTED on the dog-food domain? (§11.5)

Self-contained — uses the Anthropic SDK directly, no package code. One proposer
draft → edge_case_hunter critique → re-draft, then checks whether low-fat / sugar-free
peanut butter (xylitol) appears anywhere it wasn't put.

    export ANTHROPIC_API_KEY=...
    python scripts/validate_h2.py

Exit 0 = pass (mechanism validated), exit 1 = fail (rethink before building).
"""

from __future__ import annotations

import json
import sys

import anthropic
from pydantic import BaseModel

MODEL = "claude-sonnet-4-6"

SCHEMA = {
    "type": "object",
    "properties": {
        "food_item": {"type": "string"},
        "food_form": {
            "type": "string",
            "enum": ["standard", "low_fat", "cooked", "raw", "concentrated"],
        },
        "dog_weight_kg": {"type": "number"},
    },
}

# The deliberately-thin source logic. Note: it does NOT mention xylitol or peanut butter.
SKILL = (
    "You are a dog food safety assistant. Given a food item and a dog's profile, "
    "answer whether the dog can safely eat it. Consider known toxic foods "
    "(chocolate, grapes, onions). When in doubt, say no."
)


class Node(BaseModel):
    condition: str
    outcome: str


class Tree(BaseModel):
    nodes: list[Node]
    default_outcome: str


class Critique(BaseModel):
    missing_cases: list[str]


def _xylitol_surfaced(text: str) -> bool:
    t = text.lower()
    return "xylitol" in t or (
        "peanut butter" in t
        and ("low_fat" in t or "low-fat" in t or "sugar-free" in t or "sugar free" in t)
    )


def main() -> int:
    client = anthropic.Anthropic()

    draft = client.messages.parse(
        model=MODEL,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        system="You compile decision logic into a flat decision tree over the schema's features.",
        messages=[
            {
                "role": "user",
                "content": f"SKILL:\n{SKILL}\n\nSCHEMA:\n{json.dumps(SCHEMA)}\n\nDraft the decision tree.",
            }
        ],
        output_format=Tree,
    ).parsed_output

    crit = client.messages.parse(
        model=MODEL,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        system=(
            "You are an edge_case_hunter reviewing a decision tree: seek rare "
            "combinations of feature values the tree mishandles. List concrete missing cases."
        ),
        messages=[
            {
                "role": "user",
                "content": f"SCHEMA:\n{json.dumps(SCHEMA)}\n\nTREE:\n{draft.model_dump_json(indent=2)}\n\n"
                "What rare-but-real cases does this tree miss?",
            }
        ],
        output_format=Critique,
    ).parsed_output

    blob = draft.model_dump_json() + "\n" + "\n".join(crit.missing_cases)
    print("Proposer tree:")
    for n in draft.nodes:
        print(f"  if ({n.condition}) -> {n.outcome}")
    print(f"  default -> {draft.default_outcome}\n")
    print("edge_case_hunter missing cases:")
    for c in crit.missing_cases:
        print(f"  • {c}")

    passed = _xylitol_surfaced(blob)
    print(
        "\n"
        + (
            "PASS ✓ — xylitol / low-fat peanut butter surfaced unprompted."
            if passed
            else "FAIL ✗ — xylitol did NOT surface. Rethink domain/personas before building."
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
