"""Compile orchestration — the library layer between the loop and any front-end.

One decision, end to end: run the loop, export the tree, write the validation
dataset + behavior-lock tests, render the tempered skill. The `ingest` command,
`guide`/`audit`'s temper path, and `decompose --temper-each` all drive THIS —
so a fix here fixes all three. Everything returns data; rendering (Rich panels,
prompts) stays in cli.py, so a CI step or agent can import this without typer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .backends import Backend
from .export_skill import render_tempered_skill, weave_tempered_skill
from .export_tree import (
    enrich_validation,
    load_validation,
    merge_cases,
    write_dataset_and_tests,
)
from .ingest import ingest_skill
from .tree import DecisionTree


def load_schema(spec: str):
    """Load a pinned schema: 'file.py:ClassName' (Pydantic model) or a .json JSON Schema."""
    if spec.endswith(".json"):
        return json.loads(Path(spec).read_text())
    path, sep, cls = spec.partition(":")
    if not sep:
        raise ValueError("schema must be 'file.py:ClassName' or a path ending in .json")
    import importlib.util
    import sys
    s = importlib.util.spec_from_file_location("_temper_pinned_schema", path)
    mod = importlib.util.module_from_spec(s)
    sys.modules[s.name] = mod  # so Pydantic can resolve string annotations (Literal, etc.)
    s.loader.exec_module(mod)
    return getattr(mod, cls)


@dataclass
class SuiteResult:
    """The test-suite artifacts a compile produced (the loop's proposed cases)."""

    cases: int
    disputes: int
    test_path: str
    dataset_path: str
    enriched: list[dict]  # full rows, for rendering / manifests


@dataclass
class CompileResult:
    tree: DecisionTree
    tree_path: str
    skill_path: str | None      # None when skill_style=None (e.g. decompose orchestrates)
    suite: SuiteResult | None   # None when the loop proposed no cases
    weave_error: str | None = None  # woven render failed; template fallback was used


def write_validation_artifacts(tree: DecisionTree, out: str) -> SuiteResult | None:
    """Emit the committed validation dataset + behavior-lock tests (same artifacts as
    export_tree): <stem>.validation.jsonl (the debate surface), test_<stem>.py (always
    green), and test_<stem>_ratified.py (only if a case is ratified). Disagreements are
    data, not tests. Returns None if the loop proposed no cases."""
    proposed = getattr(tree, "proposed_examples", None)
    if not proposed:
        return None
    stem = str(Path(out).with_suffix(""))
    merged = merge_cases(load_validation(stem + ".validation.jsonl"), proposed)
    enriched = enrich_validation(tree, merged)
    write_dataset_and_tests(tree, out, enriched)
    return SuiteResult(
        cases=len(enriched),
        disputes=sum(1 for e in enriched if e["agrees"] is False),
        test_path=str(Path(out).with_name("test_" + Path(out).name)),
        dataset_path=stem + ".validation.jsonl",
        enriched=enriched,
    )


def compile_tree(
    skill: str,
    backend: Backend,
    *,
    out_dir: str = ".",
    stem: str | None = None,
    profile: str = "standard",
    schema=None,
    fn_name: str | None = None,
    examples: list[dict] | None = None,
    propose_examples: bool = True,
    gate=None,
    confirm=None,
    checkpoint=None,
    skill_style: str | None = "template",
    skill_out: str | None = None,
) -> CompileResult:
    """Freeze one decision: loop → tree .py → validation dataset + tests → tempered skill.

    ``stem`` names the output files (defaults to the decision's fn_name, known only
    after the loop). ``skill_style`` None skips the tempered skill (a flow's decisions
    are stitched by an orchestrator instead); "woven" falls back to the deterministic
    template on any model failure, recorded in ``weave_error``.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    tree = ingest_skill(
        skill, schema=schema, profile=profile, backend=backend,
        gate=gate, confirm=confirm, examples=examples,
        fn_name=fn_name, propose_examples=propose_examples, checkpoint=checkpoint,
    )
    tree_path = str(Path(out_dir) / f"{stem or fn_name or tree.fn_name}.py")
    tree.export(tree_path)
    suite = write_validation_artifacts(tree, tree_path)

    skill_path = None
    weave_error = None
    if skill_style is not None:
        module = Path(tree_path).with_suffix("").name
        skill_path = skill_out or str(Path(tree_path).with_suffix("")) + ".tempered.md"
        Path(skill_path).parent.mkdir(parents=True, exist_ok=True)
        original = Path(skill).read_text()
        if skill_style == "woven":
            try:
                md = weave_tempered_skill(tree, module, original, backend)
            except Exception as e:
                weave_error = str(e)
                md = render_tempered_skill(tree, module, original_skill_text=original)
        else:
            md = render_tempered_skill(tree, module, original_skill_text=original)
        Path(skill_path).write_text(md)

    return CompileResult(tree=tree, tree_path=tree_path, skill_path=skill_path,
                         suite=suite, weave_error=weave_error)


def tree_manifest(tree: DecisionTree, tree_path: str, skill_path: str | None) -> dict:
    """The agent-facing result of a temper run — paths + what an agent must relay."""
    proposed = getattr(tree, "proposed_examples", None) or []
    validation_path = str(Path(tree_path).with_suffix("")) + ".validation.jsonl"
    report = getattr(tree, "example_report", None)
    return {
        "fn_name": tree.fn_name,
        "tree_path": tree_path,
        "tempered_skill_path": skill_path,
        "validation_dataset_path": validation_path if proposed else None,
        "validation_case_count": len(proposed),
        "features": list(tree.features),
        "node_count": len(tree.nodes),
        "profile": tree.profile,
        "model": tree.model,
        "generated_at": tree.generated_at,
        "gray_zones": [
            {"node": i, "condition": n.condition, "note": n.gray_zone}
            for i, n in enumerate(tree.nodes, start=1)
            if n.gray_zone
        ],
        "ratified_examples": (
            {
                "agreements": report.agreements,
                "total": report.total,
                "disagreements": [
                    {"input": d.input, "expected": d.expected, "predicted": d.predicted}
                    for d in report.disagreements
                ],
            }
            if report is not None
            else None
        ),
    }
