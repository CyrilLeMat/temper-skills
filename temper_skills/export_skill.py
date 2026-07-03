"""Close the loop: emit a tempered skill.md that DELEGATES the decision to the tree.

The original skill asked the model to re-derive the decision from prose every time.
The tempered skill keeps the model's real jobs — turning the request into structured
features, and phrasing the answer — but freezes the *decision* in the deterministic
tree (§2.5: the model extracts and phrases; the tree decides). Deterministic template,
no LLM.

The pydantic-free rendering + spec skill-dir arrangement lives in ``skill_render`` (so it can
be vendored into the subagent skill's ``scripts/``); this module re-exports it and adds the
LLM-facing *woven* variant (``weave_tempered_skill``, needs pydantic) plus the CLI.

    python -m temper_skills.export_skill tree.json dog_food_checker [skill.tempered.md | skill-dir/] [orig_skill.md]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from .export_tree import tree_from_dict
from .skill_render import (  # re-exported for the library/CLI (all pydantic-free)
    arrange_skill_dir,
    module_call,
    render_orchestrator_skill,
    render_tempered_skill,
    skill_name,
)
from .tree import DecisionTree

__all__ = [
    "arrange_skill_dir",
    "render_tempered_skill",
    "render_orchestrator_skill",
    "weave_tempered_skill",
    "WovenSkill",
    "skill_name",
    "module_call",
    "main",
]


class WovenSkill(BaseModel):
    markdown: str = Field(description="The complete rewritten skill.md, ready to save.")


WEAVE_SYSTEM = (
    "You revise an agent's skill/prompt so it DELEGATES its decision to a frozen, "
    "deterministic decision tree, while preserving the skill's voice, role, and any "
    "instructions unrelated to the decision. You never invent new policy or new rules — "
    "the tree is the single source of the decision now."
)


def _render_nodes(tree: DecisionTree) -> str:
    lines = [f"  if ({n.condition}) -> {n.outcome}" for n in tree.nodes]
    lines.append(f"  default -> {tree.default_outcome}")
    return "\n".join(lines)


def weave_tempered_skill(
    tree: DecisionTree,
    module: str,
    original_skill_text: str,
    backend,
    fn: str | None = None,
) -> str:
    """LLM-rewrite the original skill to delegate to the tree (preserves voice).

    Falls back to the deterministic template at the call site if the backend fails.
    """
    fn = fn or tree.fn_name
    feats = tree.features or ["<feature>"]
    gray = [n.gray_zone for n in tree.nodes if n.gray_zone]
    user = (
        "ORIGINAL SKILL (preserve its voice, role, and any non-decision instructions):\n"
        f"{original_skill_text}\n\n"
        "The decision logic has been compiled into this deterministic tree (do NOT restate "
        f"its rules as prose — call it):\n{_render_nodes(tree)}\n\n"
        "Rewrite the skill so it DELEGATES the decision to the tree. Requirements:\n"
        f"- Keep the original role and voice; drop only the prose that re-derived the decision.\n"
        f"- Instruct the agent to (1) extract the structured features {feats} from the request, "
        f"(2) call `from {module} import {fn}` then `verdict = {module_call(module, fn, feats)}`, "
        f"(3) relay the verdict and NEVER override or re-derive it; pass a missing feature as None.\n"
        + (
            "- Surface these gray zones as caveats when relevant: " + "; ".join(gray) + "\n"
            if gray
            else ""
        )
        + "- Do NOT invent new rules, foods, categories, or thresholds — only re-route to the tree.\n"
        "Return the COMPLETE skill.md as markdown, ready to save, with no preamble."
    )
    return backend.complete(WEAVE_SYSTEM, user, WovenSkill).markdown


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print(
            "usage: python -m temper_skills.export_skill <tree.json> <module> "
            "[out.md | skill-dir/] [original_skill.md]\n"
            "  out.md      → single tempered skill file (with frontmatter)\n"
            "  skill-dir/  → spec-compliant Agent Skill: <dir>/SKILL.md + scripts/<module>.py "
            "+ assets/ (schema + validation dataset when the tree carries proposals)",
            file=sys.stderr,
        )
        return 2
    tree_path, module = argv[0], argv[1]
    out = argv[2] if len(argv) > 2 else "skill.tempered.md"
    original = open(argv[3]).read() if len(argv) > 3 else None
    data = json.loads(open(tree_path).read())
    tree = tree_from_dict(data)
    tree.proposed_examples = data.get("proposed_examples")  # carry proposals into the dataset/tests

    out_p = Path(out)
    # Legacy single-file mode: an explicit *.md target that isn't itself a SKILL.md.
    if out_p.suffix == ".md" and out_p.name != "SKILL.md":
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(render_tempered_skill(tree, module, original_skill_text=original))
        print(f"wrote {out_p}")
        return 0

    # Directory mode: emit a full spec-compliant Agent Skill folder (SKILL.md + scripts/ +
    # assets/) via arrange_skill_dir. The skill `name` must match its parent directory, so we
    # sanitize the requested dir name and write into that folder.
    requested = out_p.parent if out_p.name == "SKILL.md" else out_p
    name = skill_name(requested.name)
    skill_dir = requested.parent / name
    arrange_skill_dir(
        str(skill_dir), name, [{"tree": tree, "module": module}], original_skill_text=original
    )
    note = (
        ""
        if requested.name == name
        else f" (renamed from '{requested.name}' to a valid skill name)"
    )
    print(f"wrote {skill_dir}/ (SKILL.md + scripts/{module}.py)  · name: {name}{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
