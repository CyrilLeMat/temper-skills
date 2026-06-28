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

from .tree import DecisionNode, DecisionTree


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
    tree = tree_from_dict(json.loads(raw))
    tree.export(out)
    print(f"exported {out} ({len(tree.nodes)} nodes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
