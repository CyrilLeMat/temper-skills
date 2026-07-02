"""Validation harness (§4.5): run a compiled tree against a held-out labeled set.

The adversarial loop measures consistency, not correctness. This is the only
correctness signal — and because the tree is a pure function, it can be pinned in
CI (the H1 payoff: a prompt can't be, a deterministic tree can). Every disagreement
is the high-value output: each is either a tree bug or a mislabeled example, and
both are worth knowing before shipping.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from .export_tree import tree_from_dict
from .tree import DecisionTree

Comparator = Callable[[str, str], bool]


def exact_match(predicted: str, expected: str) -> bool:
    return predicted == expected


def _label(s: str) -> str:
    # leading token, lowercased: "no — toxic" -> "no"; "escalate_urgent" -> "escalate_urgent"
    head = s.strip().split()[0] if s.strip() else ""
    return head.lower().rstrip(":,.—-")


def label_match(predicted: str, expected: str) -> bool:
    """Compare only the leading label token — tolerant of descriptive outcomes."""
    return _label(predicted) == _label(expected)


COMPARATORS: dict[str, Comparator] = {"exact": exact_match, "label": label_match}


@dataclass
class Disagreement:
    input: dict
    expected: str
    predicted: str


@dataclass
class ValidationReport:
    total: int
    agreements: int
    disagreements: list[Disagreement] = field(default_factory=list)

    @property
    def agreement_rate(self) -> float:
        return self.agreements / self.total if self.total else 1.0

    def passed(self, min_agreement: float = 1.0) -> bool:
        return self.agreement_rate >= min_agreement


def run_validation(
    fn: Callable[[dict], str],
    dataset: list[dict],
    comparator: Comparator = exact_match,
) -> ValidationReport:
    """Run ``fn`` over ``dataset`` ([{"input": dict, "expected": str}, ...])."""
    agreements = 0
    disagreements: list[Disagreement] = []
    for entry in dataset:
        inp = entry["input"]
        expected = entry["expected"]
        try:
            predicted = fn(inp)
        except Exception as e:  # a crashing branch is itself a finding
            predicted = f"ERROR: {type(e).__name__}: {e}"
        if comparator(predicted, expected):
            agreements += 1
        else:
            disagreements.append(Disagreement(input=inp, expected=expected, predicted=predicted))
    return ValidationReport(total=len(dataset), agreements=agreements, disagreements=disagreements)


# --- loaders: turn an artifact into a callable decide(case) -> str ---

def fn_from_tree(tree: DecisionTree) -> Callable[[dict], str]:
    ns: dict = {}
    exec(compile(tree.to_source(), f"<{tree.fn_name}>", "exec"), ns)
    return ns[tree.fn_name]


def fn_from_json(path: str) -> Callable[[dict], str]:
    return fn_from_tree(tree_from_dict(json.loads(open(path).read())))


def fn_from_pyfile(path: str, fn_name: str | None = None) -> Callable[[dict], str]:
    ns: dict = {}
    exec(compile(open(path).read(), path, "exec"), ns)
    if fn_name:
        return ns[fn_name]
    fns = [v for k, v in ns.items() if callable(v) and not k.startswith("_")]
    if len(fns) != 1:
        raise ValueError(
            f"{path} defines {len(fns)} functions; pass fn_name to disambiguate."
        )
    return fns[0]


def load_dataset(path: str) -> list[dict]:
    """Load a labeled set, dropping cases not yet ratified.

    The loop can *propose* test cases (tagged ``"status": "proposed"``), but a
    machine-authored label must never gate anything until a human ratifies it — so
    proposed entries are skipped here. An entry with no ``status`` is treated as
    ratified (the hand-authored sets predate the field).

    Accepts a JSON array or JSONL (the skill-dir ``assets/*.validation.jsonl``)."""
    text = open(path).read()
    if path.endswith(".jsonl"):
        data = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    else:
        data = json.loads(text)
    return [e for e in data if e.get("status") != "proposed"]
