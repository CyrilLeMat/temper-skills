# VENDORED from temper_skills/validation_case.py — DO NOT EDIT.
# Regenerate: python -m temper_skills.vendor_scripts  (CI checks these stay in sync).
# Run standalone: python scripts/validation_case.py ...  (stdlib only, no install needed).
"""The validation-case contract — the one place the dataset row shape is defined.

A case is born in the loop (a persona proposes input + expected + rationale), merged
into the accumulating ``<stem>.validation.jsonl`` (dedup by input, provenance appended),
and enriched against the current tree (prediction + agreement recomputed every run).
Those three stages live in distill.py, export_tree.py, and skill_render.py — before this
module each re-declared the keys by hand, so adding a field meant three coordinated
edits and a rename was a silent data drop.

Rows stay plain dicts on disk and across module boundaries (JSONL); construct them via
``ValidationCase(...).to_record()`` and parse via ``from_dict`` so the shape is checked
in one place. Stdlib-only ON PURPOSE: export_tree/skill_render/update_validation are
vendored into the subagent skill's ``scripts/`` (no third-party deps), so this must be a
dataclass, not Pydantic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields

# proposed  = panel-authored, ungated; never a CI gate.
# resolved  = the proposer settled a contested cell (no domain oracle available).
# ratified  = a human domain owner blessed the label — authoritative ground truth.
STATUSES = ("proposed", "resolved", "ratified")

# Loop provenance, carried through merges untouched (in this record order).
PROVENANCE_KEYS = ("source", "round", "first_seen_round", "run_id")


def canon(inp: dict) -> str:
    """Stable dedup key for a case input (feature order-independent)."""
    return json.dumps(inp, sort_keys=True, ensure_ascii=False, default=str)


@dataclass
class ValidationCase:
    input: dict
    expected: str = ""
    rationale: str = ""
    status: str = "proposed"
    # Provenance (optional; see PROVENANCE_KEYS):
    source: str | None = None
    round: int | None = None
    first_seen_round: int | None = None
    run_id: str | None = None
    # Enrichment — computed against the CURRENT tree by enrich_validation, never
    # authored. agrees is tri-state: None = no label to compare (or the tree errored).
    tree_prediction: str | None = None
    agrees: bool | None = None

    @classmethod
    def from_dict(cls, row: dict) -> ValidationCase:
        """Parse a loose row, tolerating unknown keys — old datasets stay loadable."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in row.items() if k in known})

    def to_record(self) -> dict:
        """The canonical dict row. Key order is stable (it is the on-disk JSONL diff
        surface); enrichment keys appear only on enriched rows (tree_prediction set),
        provenance keys only when present."""
        rec: dict = {"input": self.input, "expected": self.expected, "rationale": self.rationale}
        if self.tree_prediction is not None:
            rec["tree_prediction"] = self.tree_prediction
            rec["agrees"] = self.agrees
        rec["status"] = self.status
        if self.source:
            rec["source"] = self.source
        for key in ("round", "first_seen_round", "run_id"):
            val = getattr(self, key)
            if val is not None:
                rec[key] = val
        return rec

    def key(self) -> str:
        return canon(self.input)
