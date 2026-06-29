"""Interactive CLI — the loop is not a black box; the user sees each round (§4.3)."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from pathlib import Path

from .backends import get_backend
from .distill import PROFILES, RoundResult
from .export_skill import render_tempered_skill, weave_tempered_skill
from .export_tree import tree_from_dict
from .incremental import recrystallize, render_diff
from .export_schema import _classname, normalization_notes, render_schema_source
from .ingest import InferredSchema, ingest_skill
from .sources import Sources
from .validate import COMPARATORS, fn_from_json, fn_from_pyfile, load_dataset, run_validation

import json as _json

app = typer.Typer(add_completion=False, help="Temper-Skills: prompt logic -> deterministic code.")
console = Console()


@app.callback()
def _main() -> None:
    """Temper-Skills CLI. See `ingest`."""


def _load_schema(spec: str):
    """Load a pinned schema: 'file.py:ClassName' (Pydantic model) or a .json JSON Schema."""
    if spec.endswith(".json"):
        return _json.loads(open(spec).read())
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

_VERDICT_MARK = {"ok": "[green]✓[/]", "missing_case": "[yellow]⚠[/]",
                 "collapsible": "[yellow]⚠[/]", "contradiction": "[red]✗[/]"}


def _confirm_schema(inferred: InferredSchema, auto: bool = False) -> bool:
    lines = [f"Decision function: [bold]{inferred.fn_name}[/]", "", "Inferred schema:"]
    for f in inferred.features:
        desc = f"  — {f.description}" if f.description else ""
        lines.append(f"  • {f.name}: {f.type}{desc}")
    if inferred.constraints:
        lines.append("\nInferred constraints:")
        for c in inferred.constraints:
            lines.append(f"  • {c}  [hard]")
    console.print(Panel("\n".join(lines), title="Inferred from skill", border_style="cyan"))
    if auto:
        console.print("[dim]schema auto-accepted (-y) — inferred, not human-ratified[/]")
        return True
    return Prompt.ask("Accept schema?", choices=["y", "n"], default="y") == "y"


def _clip(text: str, limit: int = 200) -> str:
    """First sentence (or a hard cap) — round panels show the gist, not paragraphs."""
    text = " ".join((text or "").split())
    cut = text.find(". ")
    if 0 < cut + 1 <= limit:
        return text[: cut + 1]
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _make_gate(interactive: bool):
    def gate(r: RoundResult) -> str:
        bits = []
        if r.ratified_count:
            pct = (r.agreement or 0) * 100
            color = "green" if (r.agreement or 0) >= 1.0 else "red"
            flag = "" if (r.agreement or 0) >= 1.0 else " ⚠ regressed"
            passed = round((r.agreement or 0) * r.ratified_count)
            bits.append(f"[{color}]{passed}/{r.ratified_count} ratified ({pct:.0f}%){flag}[/]")
        if r.proposed_count:
            ppct = 100 * r.proposed_passed / r.proposed_count
            bits.append(f"[cyan]{r.proposed_passed}/{r.proposed_count} proposed ({ppct:.0f}%)[/]")
        validation = "   ✎ validation set — tree passes " + (", ".join(bits) if bits else "0 cases (none yet)")
        body = [
            f"[bold]Round {r.round}/{r.max_rounds}[/]   "
            f"convergence estimate: {r.arbitration.convergence_estimate}%   "
            f"persona scores: min {r.min_score}/10, mean {r.mean_score}/10",
            f"{validation}   ·   tree: {len(r.tree.nodes)} nodes",
            "",
        ]
        for v in sorted(r.verdicts, key=lambda x: x.score):
            mark = _VERDICT_MARK.get(v.verdict, "•")
            body.append(f"  {mark} [bold]{v.persona}[/] {v.score}/10 — {_clip(v.detail)}")
        console.print(Panel("\n".join(body), border_style="blue"))

        if not interactive:
            return "continue"
        choice = Prompt.ask(
            "Continue [Enter] · Stop and review [s] · Abort [q]",
            choices=["", "s", "q"], default="", show_choices=False,
        )
        return {"": "continue", "s": "stop", "q": "abort"}[choice]

    return gate


@app.command()
def ingest(
    skill: str = typer.Argument(..., help="Path to the skill.md to migrate."),
    profile: str = typer.Option("standard", help=f"One of {list(PROFILES)}."),
    out: str = typer.Option("decision_tree.generated.py", help="Output .py path."),
    model: str = typer.Option("claude-sonnet-4-6", help="Model: any LiteLLM id (claude-sonnet-4-6, openai/gpt-4o, …)."),
    backend: str = typer.Option(
        "auto", help="LLM backend: auto | api | claude | opencode."
    ),
    examples: str = typer.Option(
        None, help="JSON file of ratified examples [{input, expected}] to check the tree against."
    ),
    skill_out: str = typer.Option(
        None, help="Where to write the tempered skill.md (default: <out>.tempered.md)."
    ),
    skill_style: str = typer.Option(
        "template", help="Tempered skill style: template (deterministic) | woven (LLM-rewritten)."
    ),
    schema: str = typer.Option(
        None, help="Pin a schema: 'file.py:ClassName' (Pydantic) or a .json JSON Schema. "
        "If omitted, the schema is inferred from the skill."
    ),
    propose_schema: bool = typer.Option(
        False, "--propose-schema",
        help="Draft the schema from the skill, write it to schema.proposed.py for you to "
             "review/edit, then STOP. Re-run pinning it with --schema to distill. The loop "
             "never runs on an unratified schema."),
    fn: str = typer.Option(None, help="Decision function name (used with --schema)."),
    yes: bool = typer.Option(False, "--yes", "-y",
                             help="Non-interactive: auto-accept the inferred schema and don't stop "
                                  "at each round — run to convergence/cap (panels still print)."),
    propose_examples: bool = typer.Option(
        True, "--propose-examples/--no-propose-examples",
        help="Have the loop draft discriminating test cases for its gray zones, for you "
             "to ratify and feed back via --examples (written to <out>.proposed_examples.json)."),
    require_fit: bool = typer.Option(
        False, "--require-fit",
        help="Run the fitness audit first and abort (exit 3) if the verdict is 'skip' — "
             "so a pipeline won't burn the loop on a known bad fit (e.g. a flat lookup)."),
):
    """Compile a skill's decision logic into a deterministic Python tree."""
    interactive = PROFILES[profile][2] and not yes
    try:
        be = get_backend(backend, model)
    except (ValueError, RuntimeError) as e:
        console.print(f"[red]Backend error:[/] {e}")
        raise typer.Exit(1)
    if require_fit:
        from .audit import audit_skill
        rep = audit_skill(skill, backend=be)
        if rep.verdict == "skip":
            console.print(f"[red]Not a temper fit:[/] {'; '.join(rep.reasons)}  "
                          "[dim](drop --require-fit to override)[/]")
            raise typer.Exit(3)
        console.print(f"[green]fitness: {rep.verdict}[/]"
                      + (f"  ⚠ {'; '.join(rep.caveats)}" if rep.caveats else ""))
    if propose_schema:
        if schema:
            console.print("[red]--propose-schema and --schema are mutually exclusive[/] "
                          "(--propose-schema drafts a schema; --schema pins one).")
            raise typer.Exit(2)
        inferred = ingest_skill(skill, schema=None, backend=be, propose_schema_only=True)
        out_path = Path("schema.proposed.py")
        out_path.write_text(render_schema_source(inferred))
        _print_proposed_schema(inferred, out_path, skill)
        raise typer.Exit(0)

    pinned = _load_schema(schema) if schema else None
    ratified = load_dataset(examples) if examples else None
    console.print(f"[cyan]Reading {skill}[/]  ·  backend: [bold]{be.describe()}[/]"
                  + (f"  ·  schema: {schema}" if schema else "  ·  schema: inferred")
                  + (f"  ·  {len(ratified)} ratified example(s)" if ratified else ""))
    try:
        tree = ingest_skill(
            skill, schema=pinned, profile=profile, backend=be,
            gate=_make_gate(interactive),
            confirm=(lambda i: _confirm_schema(i, auto=True)) if yes else _confirm_schema,
            examples=ratified, fn_name=fn,
            propose_examples=propose_examples,
        )
    except KeyboardInterrupt as e:
        console.print(f"[red]Aborted:[/] {e}")
        raise typer.Exit(1)
    tree.export(out)
    cost = be.cost_estimate()
    cost_line = f"~${cost:.4f} (metered)" if cost is not None else "subscription — no metered cost"
    console.print(Panel(tree.to_source(), title=f"Exported {out}", border_style="green"))
    _print_example_check(tree)
    _write_proposed_examples(tree, out)

    # Close the loop: a tempered skill.md that delegates the decision to the tree.
    module = Path(out).with_suffix("").name
    md_path = skill_out or str(Path(out).with_suffix("")) + ".tempered.md"
    with open(skill) as f:
        original = f.read()
    if skill_style == "woven":
        try:
            md = weave_tempered_skill(tree, module, original, be)
        except Exception as e:
            console.print(f"[yellow]weave failed ({e}); falling back to deterministic template[/]")
            md = render_tempered_skill(tree, module, original_skill_text=original)
    else:
        md = render_tempered_skill(tree, module, original_skill_text=original)
    Path(md_path).write_text(md)
    console.print(f"[green]✓ tempered skill ({skill_style}) → {md_path}[/]  (delegates the decision to {module}.{tree.fn_name})")
    console.print(f"[dim]backend {be.describe()} · cost: {cost_line}[/]")


def _print_example_check(tree) -> None:
    """Surface the ratified-examples check (if any examples were provided)."""
    r = getattr(tree, "example_report", None)
    if r is None:
        return
    if not r.disagreements:
        console.print(f"[green]✓ ratified examples: {r.agreements}/{r.total} agree[/]")
        return
    lines = [f"[red]{r.agreements}/{r.total} ratified examples agree[/] — "
             "each disagreement is a tree bug or a mislabeled example; sign off:"]
    for d in r.disagreements:
        lines.append(f"  input={d.input}")
        lines.append(f"    expected [green]{d.expected}[/]  ·  got [red]{d.predicted}[/]")
    console.print(Panel("\n".join(lines), title="⚠ ratified-example disagreements",
                        border_style="yellow"))


def _print_proposed_schema(inferred: InferredSchema, path: Path, skill: str) -> None:
    """Surface the drafted contract + its normalization burden, awaiting ratification."""
    notes = normalization_notes(inferred)
    lines = [f"Decision function: [bold]{inferred.fn_name}[/]",
             f"Class: [bold]{_classname(inferred.fn_name)}[/]", "", "Fields:"]
    for f in inferred.features:
        warn = f"   [yellow]⚠ {notes[f.name]}[/]" if f.name in notes else ""
        lines.append(f"  • {f.name}: {f.type}{warn}")
    if inferred.constraints:
        lines.append("\nInferred constraints (review, then pass via --constraint):")
        for c in inferred.constraints:
            lines.append(f"  • {c}  [hard]")
    if notes:
        lines.append("\n[dim]The tree is only as safe as the normalizer feeding these "
                     "exact-match fields. A Literal closes the space and helps the loop "
                     "converge; a bare str reopens it.[/]")
    cls = _classname(inferred.fn_name)
    lines.append(f"\n[bold]proposed labels, not ground truth.[/] Review/edit [bold]{path}[/], "
                 f"then re-run to distill:\n  [bold]temper-skills ingest {skill} "
                 f"--schema {path}:{cls}[/]")
    console.print(Panel("\n".join(lines), title="✎ proposed schema (awaiting ratification)",
                        border_style="magenta"))


def _write_proposed_examples(tree, out: str) -> None:
    """Write the loop's drafted test cases to a sidecar file for human ratification."""
    proposed = getattr(tree, "proposed_examples", None)
    if not proposed:
        return
    path = str(Path(out).with_suffix("")) + ".proposed_examples.json"
    Path(path).write_text(_json.dumps(proposed, indent=2, ensure_ascii=False))
    lines = [f"The loop drafted [bold]{len(proposed)}[/] test case(s) for its gray zones — "
             "[bold]proposed labels, not ground truth.[/] Review, fix any label, then set "
             '[bold]"status": "ratified"[/] (or move them into your validation set) and '
             "re-run with --examples to anchor these cells:"]
    for e in proposed:
        flag = "" if e["expected"] == e.get("tree_prediction") else "  [yellow](differs from tree)[/]"
        src = f" [dim]— {e['source']}[/]" if e.get("source") else ""
        lines.append(f"  input={e['input']}{src}")
        lines.append(f"    proposed [green]{e['expected']}[/]  ·  tree says [cyan]{e.get('tree_prediction')}[/]{flag}")
        lines.append(f"    [dim]{e['rationale']}[/]")
    lines.append(f"\n[dim]written to {path}[/]")
    console.print(Panel("\n".join(lines), title="✎ proposed test cases (awaiting ratification)",
                        border_style="magenta"))


@app.command()
def incremental(
    prior: str = typer.Argument(..., help="Prior tree.json to evolve."),
    skill: str = typer.Option(None, help="Updated skill.md to fold in (optional)."),
    constraint: list[str] = typer.Option([], "--constraint", "-c",
                                          help="New HARD constraint (repeatable)."),
    profile: str = typer.Option("standard", help=f"One of {list(PROFILES)}."),
    out: str = typer.Option("decision_tree.generated.py", help="Output .py path."),
    model: str = typer.Option("claude-sonnet-4-6", help="Model: any LiteLLM id (claude-sonnet-4-6, openai/gpt-4o, …)."),
    backend: str = typer.Option("auto", help="auto | api | claude | opencode."),
    fn: str = typer.Option(None, help="Override the function name."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Don't stop at each round."),
):
    """Re-crystallize an existing tree against new constraints/sources; show the diff."""
    prior_tree = tree_from_dict(_json.loads(open(prior).read()))
    schema = {"type": "object",
              "properties": {f: {} for f in prior_tree.features},
              "additionalProperties": True}
    sources = Sources(
        schema=schema,
        constraints=[{"rule": c, "hard": True} for c in constraint],
        skill_text=open(skill).read() if skill else None,
    )
    try:
        be = get_backend(backend, model)
    except (ValueError, RuntimeError) as e:
        console.print(f"[red]Backend error:[/] {e}")
        raise typer.Exit(1)
    interactive = PROFILES[profile][2] and not yes
    console.print(f"[cyan]Evolving {prior}[/]  ·  backend: [bold]{be.describe()}[/]  "
                  f"·  +{len(constraint)} constraint(s)")
    try:
        new_tree, diff = recrystallize(
            prior_tree, sources, profile=profile, backend=be,
            gate=_make_gate(interactive), fn_name=fn,
        )
    except KeyboardInterrupt as e:
        console.print(f"[red]Aborted:[/] {e}")
        raise typer.Exit(1)
    new_tree.export(out)
    title = "no change" if diff.is_empty else "structural diff (v_n → v_n+1)"
    console.print(Panel(render_diff(diff), title=title, border_style="magenta"))
    console.print(Panel(new_tree.to_source(), title=f"Exported {out}", border_style="green"))


@app.command()
def validate(
    artifact: str = typer.Argument(..., help="The tree: a tree.json or an exported .py."),
    dataset: str = typer.Argument(..., help="Held-out labeled set: JSON [{input, expected}, ...]."),
    fn: str = typer.Option(None, help="Function name (for a .py with multiple defs)."),
    match: str = typer.Option("label", help=f"Comparator: {list(COMPARATORS)}."),
    min_agreement: float = typer.Option(1.0, help="Min agreement rate to pass (0–1)."),
):
    """Run the tree against a labeled set; report agreement and every disagreement.

    Exits non-zero if agreement is below the threshold — so it pins the tree in CI.
    """
    if match not in COMPARATORS:
        console.print(f"[red]--match must be one of {list(COMPARATORS)}[/]")
        raise typer.Exit(2)
    decide = fn_from_pyfile(artifact, fn) if artifact.endswith(".py") else fn_from_json(artifact)
    report = run_validation(decide, load_dataset(dataset), COMPARATORS[match])

    pct = report.agreement_rate * 100
    color = "green" if report.passed(min_agreement) else "red"
    lines = [f"Agreement: [{color}]{report.agreements}/{report.total} ({pct:.1f}%)[/]"]
    if report.disagreements:
        lines.append("\n[bold]Disagreements[/] — each is a tree bug or a mislabeled example; sign off:")
        for d in report.disagreements:
            lines.append(f"  input={d.input}")
            lines.append(f"    expected [green]{d.expected}[/]  ·  got [red]{d.predicted}[/]")
    console.print(Panel("\n".join(lines), title=f"validate {artifact}", border_style=color))
    if not report.passed(min_agreement):
        raise typer.Exit(1)


@app.command()
def audit(
    skill: str = typer.Argument(..., help="Path to the skill.md to assess for temper-fitness."),
    model: str = typer.Option("claude-sonnet-4-6", help="Model: any LiteLLM id."),
    backend: str = typer.Option("auto", help="LLM backend: auto | api | claude | opencode."),
    json_out: bool = typer.Option(False, "--json", help="Emit the FitnessReport as JSON (for a pipeline / the Evolve Server)."),
):
    """Decide whether a skill's logic is worth tempering, before spending the loop.

    Exits 0 for 'temper'/'caveats', 3 for 'skip' — so a pipeline can triage a whole
    skill library and only crystallize the fits.
    """
    from .audit import audit_skill

    try:
        be = get_backend(backend, model)
    except (ValueError, RuntimeError) as e:
        console.print(f"[red]Backend error:[/] {e}")
        raise typer.Exit(1)
    report = audit_skill(skill, backend=be)

    if json_out:
        console.print_json(report.model_dump_json())
    else:
        color = {"temper": "green", "caveats": "yellow", "skip": "red"}[report.verdict]
        body = [
            f"[{color}]verdict: {report.verdict.upper()}[/]  ·  fn: [bold]{report.fn_name}[/]",
            f"decisiveness {report.decisiveness}/10 · combinatorics {report.combinatorics}/10 "
            f"· stakes {report.stakes}/10 · schema closure {report.schema_closure:.0%}",
            "",
        ]
        body += [f"  • {r}" for r in report.reasons]
        body += [f"  [yellow]⚠[/] {c}" for c in report.caveats]
        console.print(Panel("\n".join(body), title="Temper fitness", border_style=color))
    if report.verdict == "skip":
        raise typer.Exit(3)


if __name__ == "__main__":
    app()
