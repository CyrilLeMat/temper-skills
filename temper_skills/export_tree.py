"""Deterministic tree → .py exporter, callable from the Claude Code skill.

The subagent-driven loop (see .claude/skills/temper-skills/SKILL.md) produces a
tree as JSON; this turns it into the zero-dependency Python module. No LLM here —
this is the deterministic half of the pipeline.

    python -m temper_skills.export_tree tree.json route.py
    cat tree.json | python -m temper_skills.export_tree - route.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .tree import DecisionNode, DecisionTree


def _compile(tree: DecisionTree):
    # Inline (not validate.fn_from_tree) to keep this module import-light — the
    # deterministic export path must not pull in the LLM backends.
    ns: dict = {}
    exec(compile(tree.to_source(), f"<{tree.fn_name}>", "exec"), ns)
    return ns[tree.fn_name]


def enrich_proposed(tree: DecisionTree, raw: list[dict]) -> list[dict]:
    """Stamp orchestrator-drafted cases with the tree's own prediction + a 'proposed' tag.

    The subagent loop authors ``input``/``expected``/``rationale``; the *prediction* and the
    un-ratified status are computed here deterministically, so a machine-authored label can
    never masquerade as ground truth (the same trust boundary as the library path)."""
    fn = _compile(tree)
    out: list[dict] = []
    for case in raw:
        try:
            prediction = fn(case["input"])
        except Exception as e:
            prediction = f"ERROR: {type(e).__name__}: {e}"
        record = {
            "input": case["input"],
            "expected": case.get("expected", ""),
            "rationale": case.get("rationale", ""),
            "tree_prediction": prediction,
            "status": "proposed",
        }
        if case.get("source"):
            record["source"] = case["source"]
        out.append(record)
    return out


def tree_from_dict(data: dict) -> DecisionTree:
    nodes = [
        DecisionNode(
            condition=n["condition"],
            outcome=n["outcome"],
            rounds_survived=int(n.get("rounds_survived", 1)),
            sources=list(n.get("sources", [])),
            critic_note=n.get("critic_note"),
            gray_zone=n.get("gray_zone"),
        )
        for n in data["nodes"]
    ]
    return DecisionTree(
        nodes=nodes,
        default_outcome=data["default_outcome"],
        features=list(data.get("features", [])),
        fn_name=data.get("fn_name", "decide"),
        model=data.get("model", "claude-code-subagents"),
        profile=data.get("profile", "standard"),
        constraints_version=data.get("constraints_version", "v1.0"),
        include_provenance=bool(data.get("include_provenance", True)),
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        print("usage: python -m temper_skills.export_tree <tree.json|-> <out.py>", file=sys.stderr)
        return 2
    src, out = argv
    raw = sys.stdin.read() if src == "-" else open(src).read()
    data = json.loads(raw)
    tree = tree_from_dict(data)
    tree.export(out)
    print(f"exported {out} ({len(tree.nodes)} nodes)")
    if data.get("proposed_examples"):
        enriched = enrich_proposed(tree, data["proposed_examples"])
        side = str(Path(out).with_suffix("")) + ".proposed_examples.json"
        Path(side).write_text(json.dumps(enriched, indent=2, ensure_ascii=False))
        print(f"wrote {len(enriched)} proposed test case(s) → {side} "
              f"(proposed, not ratified — review before they gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
