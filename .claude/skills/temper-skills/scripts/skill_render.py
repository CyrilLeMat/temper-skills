# VENDORED from temper_skills/skill_render.py — DO NOT EDIT.
# Regenerate: python -m temper_skills.vendor_scripts  (CI checks these stay in sync).
# Run standalone: python scripts/skill_render.py ...  (stdlib only, no install needed).
"""Render a tempered decision into a spec-compliant Agent Skill — stdlib only, no LLM.

Split out of ``export_skill`` so it carries **no pydantic dependency** and can be vendored
into the subagent skill's ``scripts/`` (see ``vendor_scripts``). ``export_skill`` re-exports
these for the library/CLI; the LLM-facing weave path (which needs pydantic) stays there.

CLI (used by subagent mode to emit a full skill dir without installing anything):

    python scripts/skill_render.py <spec.json> <skill-dir/>

where spec.json is::

    {"name": "dog-day", "description": "...", "original_skill": "input/skill.md",
     "generative_steps": ["write a note"],
     "decisions": [{"tree": "decide_walk.tree.json", "module": "decide_walk",
                    "schema": "decide_walk.schema.py", "ratified": "walk.json",
                    "consumes": ["decide_walk"]}]}

Paths inside the spec are resolved relative to the spec file. One decision → a tempered
skill; several → an orchestrator that chains them.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from export_tree import (
    enrich_validation,
    load_validation,
    merge_cases,
    render_behavior_lock,
    render_ratified,
    tree_from_dict,
)
from tree import DecisionTree


def _role_line(original: str | None) -> str:
    if original:
        for line in original.splitlines():
            s = line.strip()
            if re.match(r"(?i)^you are\b", s):
                return s.rstrip(".") + "."
    return "You are an assistant."


def skill_name(raw: str) -> str:
    """Sanitize to a spec-valid Agent Skills ``name`` (lowercase a-z0-9 + single hyphens,
    no leading/trailing/consecutive hyphens, ≤64 chars). ``dog_day`` → ``dog-day``."""
    s = re.sub(r"[^a-z0-9]+", "-", raw.strip().lower())
    s = re.sub(r"-{2,}", "-", s).strip("-")[:64].strip("-")
    return s or "skill"


def _yaml_quoted(s: str) -> str:
    """A YAML double-quoted scalar — safe for any description (colons, dashes, quotes)."""
    return '"' + " ".join(s.split()).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _frontmatter(name: str, description: str) -> list[str]:
    return ["---", f"name: {name}", f"description: {_yaml_quoted(description)[:1024]}", "---", ""]


def _default_description(tree: DecisionTree, fn: str) -> str:
    outcomes = list(dict.fromkeys([n.outcome for n in tree.nodes] + [tree.default_outcome]))
    feats = ", ".join(tree.features) or "structured features"
    return (
        f"Frozen, deterministic decision (no LLM): maps {feats} to one of "
        f"{', '.join(outcomes)}. Use when this decision must be made consistently and "
        f"auditably — extract the features, call {fn}(), and relay its verdict without overriding it."
    )


def module_call(module: str, fn: str, feats: list[str]) -> str:
    return f'{fn}({{{", ".join(f"{f!r}: {f}" for f in feats)}}})'


def render_tempered_skill(
    tree: DecisionTree,
    module: str,
    fn: str | None = None,
    original_skill_text: str | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    script_path: str | None = None,
    import_prefix: str = "",
) -> str:
    fn = fn or tree.fn_name
    role = _role_line(original_skill_text)
    feats = tree.features or ["<feature>"]
    gray = [(i, n) for i, n in enumerate(tree.nodes, 1) if n.gray_zone]

    out: list[str] = []
    out += _frontmatter(skill_name(name or module or fn),
                        description or _default_description(tree, fn))
    out.append(f"# {fn} — skill (tempered by temper-skills)")
    out.append("")
    out.append(role)
    out.append("")
    out.append(
        "**The decision is frozen.** Do not re-derive it from prose or your own judgment — "
        f"the routing logic now lives in a deterministic decision tree (`{module}.{fn}`, "
        "zero LLM calls, reviewed and version-controlled). Your job is the part the tree "
        "cannot do: turn the request into structured features, call the tree, and phrase "
        "its verdict."
    )
    out.append("")
    out.append("## How to answer")
    out.append("")
    out.append("1. Extract these structured features from the request:")
    for f in feats:
        out.append(f"   - `{f}`")
    out.append("2. Call the decision tree and treat its result as authoritative"
               + (f" (bundled at `{script_path}`):" if script_path else ":"))
    out.append("")
    out.append("   ```python")
    out.append(f"   from {import_prefix}{module} import {fn}")
    out.append("   verdict = " + fn + "({" + ", ".join(f'"{f}": {f}' for f in feats) + "})")
    out.append("   ```")
    out.append("3. Relay `verdict` to the user. **Do not override it.** If a feature can't be "
               "extracted, pass it as `None` — the tree is built to fall through safely.")
    out.append("")
    if gray:
        out.append("## Gray zones to surface")
        out.append("")
        out.append("The tree flags these as underdetermined — mention the caveat when the "
                   "answer touches them:")
        for i, n in gray:
            out.append(f"- (n{i}) {n.gray_zone}")
        out.append("")
    out.append("---")
    out.append(
        f"Generated by temper-skills from the original skill · {tree.generated_at} · "
        f"model: {tree.model}. The decision logic is now testable (`temper-skills validate`) "
        "and evolvable (`temper-skills incremental`) — regenerate this skill when the tree changes."
    )
    return "\n".join(out) + "\n"


def render_orchestrator_skill(
    name: str,
    items: list[dict],
    generative_steps: list[str] | None = None,
    original_skill_text: str | None = None,
    *,
    description: str | None = None,
    import_prefix: str = "",
) -> str:
    """A multi-tree tempered skill: the flow's orchestrator.

    Generalizes ``render_tempered_skill`` from one decision to several — the skill the
    agent runs delegates each frozen decision to its tree (respecting ``consumes`` coupling)
    and keeps only the generative steps. ``items`` is one dict per decision with keys
    ``fn``, ``module``, ``features``, ``consumes`` (fn_names it chains from), ``gray_zones``.
    ``import_prefix`` (e.g. ``"scripts."``) prefixes the tree imports for the spec skill-dir
    layout, where the trees live in ``scripts/`` and the agent runs from the skill root.
    """
    role = _role_line(original_skill_text)
    fns = ", ".join(it["fn"] for it in items) or "its decisions"
    desc = description or (
        f"Tempered orchestrator: chains frozen, deterministic decision trees ({fns}) and "
        f"keeps only the generative step(s). Use to run this flow with each decision made "
        f"by code (no LLM) and only the prose left to the model."
    )
    out = _frontmatter(skill_name(name), desc)
    out += [
        f"# {name} — orchestrator (tempered by temper-skills)",
        "",
        role,
        "",
        "**The decisions below are frozen** — extract the features, call each tree, relay the "
        "verdict, don't re-derive. Only the generative step(s) are yours to phrase. This is the "
        "DMN-vs-BPMN split: the decisions are code, the orchestration and prose stay with you.",
    ]
    for idx, it in enumerate(items, 1):
        out += ["", f"## {idx}. `{it['fn']}` — frozen"]
        if it.get("consumes"):
            out.append(f"Chained: feed the outcome of `{', '.join(it['consumes'])}` into the "
                       "matching feature below.")
        out.append("Extract " + ", ".join(f"`{f}`" for f in it["features"]) + ", then:")
        out += [
            "```python",
            f"from {import_prefix}{it['module']} import {it['fn']}",
            f"{it['fn']}_verdict = {module_call(it['module'], it['fn'], it['features'])}",
            "```",
        ]
        for gz in it.get("gray_zones", []):
            out.append(f"- gray zone: {gz}")
    if generative_steps:
        out += ["", "## Then — generation, yours"]
        for g in generative_steps:
            out.append(f"- {g}")
    out += [
        "",
        "---",
        f"Generated by `temper-skills decompose --temper-each`. Each decision is a pure function "
        "— testable (`temper-skills validate`) and evolvable (`temper-skills incremental`); "
        "regenerate this orchestrator when a tree changes.",
    ]
    return "\n".join(out) + "\n"


def arrange_skill_dir(
    skill_dir: str,
    name: str,
    decisions: list[dict],
    *,
    generative_steps: list[str] | None = None,
    original_skill_text: str | None = None,
    description: str | None = None,
) -> Path:
    """Write a spec-compliant Agent Skill folder (agentskills.io) for one or more frozen trees.

    Layout, per the spec's named directories:
      SKILL.md                          orchestrator (delegates each decision to its tree)
      scripts/<module>.py               the frozen tree (self-contained, zero deps)
      scripts/test_<module>.py          behavior-lock test (+ _ratified.py if any ratified case)
      assets/<module>.schema.py         the input schema      (spec: "Data files … schemas" → assets/)
      assets/<module>.validation.jsonl  the validation dataset (spec: data files → assets/)

    ``decisions`` is one dict per tree: ``{tree: DecisionTree, module: str,
    schema_src: str|None, consumes: list[str], ratified: list[{input, expected}]}``.
    ``ratified`` cases (human ground truth) are merged as ``status: "ratified"`` — they own
    their cell and drive ``test_<module>_ratified.py`` (the one test allowed to fail). The
    SKILL.md imports the trees as ``from scripts.<module> import <fn>`` (agent runs from the
    skill root)."""
    root = Path(skill_dir)
    name = skill_name(name)
    scripts, assets = root / "scripts", root / "assets"
    scripts.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)

    items: list[dict] = []
    for d in decisions:
        tree, module = d["tree"], d["module"]
        tree.export(str(scripts / f"{module}.py"))

        # Ratified ground truth wins its cell over panel proposals, so it goes first in the merge.
        ratified = [{"input": c["input"], "expected": c["expected"], "status": "ratified",
                     "rationale": c.get("rationale", ""), "source": c.get("source", "ratified")}
                    for c in d.get("ratified", [])]
        proposed = getattr(tree, "proposed_examples", None) or []
        val_path = assets / f"{module}.validation.jsonl"
        enriched = enrich_validation(
            tree, merge_cases(load_validation(str(val_path)), ratified + proposed))
        if enriched:
            val_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in enriched))
            (scripts / f"test_{module}.py").write_text(
                render_behavior_lock(module, tree.fn_name, enriched))
            rat = render_ratified(module, tree.fn_name, enriched)
            if rat:
                (scripts / f"test_{module}_ratified.py").write_text(rat)
        if d.get("schema_src"):
            (assets / f"{module}.schema.py").write_text(d["schema_src"])

        items.append({
            "fn": tree.fn_name, "module": module, "features": list(tree.features),
            "consumes": d.get("consumes", []),
            "gray_zones": [n.gray_zone for n in tree.nodes if n.gray_zone],
        })

    # Single decision reads naturally as a tempered skill; several read as an orchestrator.
    if len(items) == 1:
        it = items[0]
        md = render_tempered_skill(
            decisions[0]["tree"], it["module"], original_skill_text=original_skill_text,
            name=name, description=description, script_path=f"scripts/{it['module']}.py",
            import_prefix="scripts.")
    else:
        md = render_orchestrator_skill(name, items, generative_steps=generative_steps,
                                       original_skill_text=original_skill_text,
                                       description=description, import_prefix="scripts.")
    (root / "SKILL.md").write_text(md)
    return root


def _load_decision(d: dict, base: Path) -> dict:
    """Resolve a spec decision's file paths (relative to the spec) into an arrange() dict."""
    data = json.loads((base / d["tree"]).read_text())
    tree = tree_from_dict(data)
    tree.proposed_examples = data.get("proposed_examples")
    out = {"tree": tree, "module": d.get("module", tree.fn_name), "consumes": d.get("consumes", [])}
    if d.get("schema"):
        out["schema_src"] = (base / d["schema"]).read_text()
    if d.get("ratified"):
        out["ratified"] = json.loads((base / d["ratified"]).read_text())
    return out


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        print("usage: python scripts/skill_render.py <spec.json> <skill-dir/>\n"
              "  spec.json: {name, description?, original_skill?, generative_steps?, "
              "decisions:[{tree, module?, schema?, ratified?, consumes?}]}", file=sys.stderr)
        return 2
    spec_path, out_dir = argv
    base = Path(spec_path).resolve().parent
    spec = json.loads(Path(spec_path).read_text())
    decisions = [_load_decision(d, base) for d in spec["decisions"]]
    original = None
    if spec.get("original_skill"):
        original = (base / spec["original_skill"]).read_text()
    root = arrange_skill_dir(out_dir, spec["name"], decisions,
                             generative_steps=spec.get("generative_steps"),
                             original_skill_text=original, description=spec.get("description"))
    n = len(decisions)
    print(f"wrote {root}/ — SKILL.md + scripts/ ({n} tree{'s' if n != 1 else ''}) + assets/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
