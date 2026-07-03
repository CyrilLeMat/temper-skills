"""Interactive CLI — typer parsing + Rich rendering, nothing else.

Orchestration lives in pipelines.py (compile_tree and friends); this module turns
CLI options into pipeline calls and pipeline results into panels. Each command
builds its own Console (stderr in --json mode, so stdout carries only the machine
manifest) and passes it down — there is deliberately no module-global console.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from pathlib import Path

from .backends import get_backend
from .distill import PROFILES, RoundResult
from .export_tree import tree_from_dict
from .incremental import recrystallize, render_diff
from .export_schema import _classname, normalization_notes, render_schema_source
from .ingest import InferredSchema
from .pipelines import CompileResult, SuiteResult, compile_tree, load_schema, tree_manifest
from .sources import Sources
from .validate import COMPARATORS, fn_from_json, fn_from_pyfile, load_dataset, run_validation

import json as _json

app = typer.Typer(add_completion=False, help="Temper-Skills: prompt logic -> deterministic code.")


@app.callback()
def _main() -> None:
    """Temper-Skills CLI. See `ingest`."""


def _console(json_out: bool = False) -> Console:
    """The command's UI surface. JSON mode renders to stderr so stdout carries only
    the machine-readable manifest."""
    return Console(stderr=True) if json_out else Console()


_VERDICT_MARK = {
    "ok": "[green]✓[/]",
    "missing_case": "[yellow]⚠[/]",
    "collapsible": "[yellow]⚠[/]",
    "contradiction": "[red]✗[/]",
}


def _confirm_schema(ui: Console, inferred: InferredSchema, auto: bool = False) -> bool:
    lines = [f"Decision function: [bold]{inferred.fn_name}[/]", "", "Inferred schema:"]
    for f in inferred.features:
        desc = f"  — {f.description}" if f.description else ""
        lines.append(f"  • {f.name}: {f.type}{desc}")
    if inferred.constraints:
        lines.append("\nInferred constraints:")
        for c in inferred.constraints:
            lines.append(f"  • {c}  [hard]")
    ui.print(Panel("\n".join(lines), title="Inferred from skill", border_style="cyan"))
    if auto:
        ui.print("[dim]schema auto-accepted (-y) — inferred, not human-ratified[/]")
        return True
    return Prompt.ask("Accept schema?", choices=["y", "n"], default="y") == "y"


def _clip(text: str, limit: int = 200) -> str:
    """First sentence (or a hard cap) — round panels show the gist, not paragraphs."""
    text = " ".join((text or "").split())
    cut = text.find(". ")
    if 0 < cut + 1 <= limit:
        return text[: cut + 1]
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _emit_json(obj) -> None:
    """Write the machine-readable manifest to real stdout (not the Rich console)."""
    print(_json.dumps(obj, indent=2, ensure_ascii=False))


def _make_gate(ui: Console, interactive: bool):
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
        validation = "   ✎ validation set — tree passes " + (
            ", ".join(bits) if bits else "0 cases (none yet)"
        )
        conv = r.arbitration.convergence_estimate
        ccolor = "green" if conv >= 80 else "yellow" if conv >= 50 else "red"
        body = [
            f"[bold]Round {r.round}/{r.max_rounds}[/]   "
            f"[{ccolor}]settled: {conv}%[/]   "
            f"[dim]panel: harshest critic {r.min_score}/10 · mean {r.mean_score}/10 "
            "(opposing critics — a mid spread is normal)[/]",
            f"{validation}   ·   tree: {len(r.tree.nodes)} nodes",
            "",
        ]
        for v in sorted(r.verdicts, key=lambda x: x.score):
            mark = _VERDICT_MARK.get(v.verdict, "•")
            body.append(f"  {mark} [bold]{v.persona}[/] {v.score}/10 — {_clip(v.detail)}")
        ui.print(Panel("\n".join(body), border_style="blue"))

        if not interactive:
            return "continue"
        choice = Prompt.ask(
            "Continue [Enter] · Stop and review [s] · Abort [q]",
            choices=["", "s", "q"],
            default="",
            show_choices=False,
        )
        return {"": "continue", "s": "stop", "q": "abort"}[choice]

    return gate


@app.command()
def ingest(
    skill: str = typer.Argument(..., help="Path to the skill.md to migrate."),
    profile: str = typer.Option("standard", help=f"One of {list(PROFILES)}."),
    out: str = typer.Option("decision_tree.generated.py", help="Output .py path."),
    model: str = typer.Option(
        "claude-sonnet-4-6", help="Model: any LiteLLM id (claude-sonnet-4-6, openai/gpt-4o, …)."
    ),
    backend: str = typer.Option("auto", help="LLM backend: auto | api | claude | opencode."),
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
        None,
        help="Pin a schema: 'file.py:ClassName' (Pydantic) or a .json JSON Schema. "
        "If omitted, the schema is inferred from the skill.",
    ),
    propose_schema: bool = typer.Option(
        False,
        "--propose-schema",
        help="Draft the schema from the skill, write it to schema.proposed.py for you to "
        "review/edit, then STOP. Re-run pinning it with --schema to distill. The loop "
        "never runs on an unratified schema.",
    ),
    fn: str = typer.Option(None, help="Decision function name (used with --schema)."),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Non-interactive: auto-accept the inferred schema and don't stop "
        "at each round — run to convergence/cap (panels still print).",
    ),
    propose_examples: bool = typer.Option(
        True,
        "--propose-examples/--no-propose-examples",
        help="Have the loop draft discriminating test cases for its gray zones, for you "
        "to ratify and feed back via --examples (written to <out>.validation.jsonl).",
    ),
    require_fit: bool = typer.Option(
        False,
        "--require-fit",
        help="Run the fitness audit first and abort (exit 3) if the verdict is 'skip' — "
        "so a pipeline won't burn the loop on a known bad fit (e.g. a flat lookup).",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emit a machine-readable result manifest to stdout (paths, gray zones, proposed "
        "examples); human panels go to stderr. Implies non-interactive (auto-accepts the "
        "inferred schema, runs to convergence) — for agents/pipelines driving the CLI.",
    ),
):
    """Compile a skill's decision logic into a deterministic Python tree."""
    ui = _console(json_out)
    interactive = PROFILES[profile][2] and not yes and not json_out
    try:
        be = get_backend(backend, model)
    except (ValueError, RuntimeError) as e:
        ui.print(f"[red]Backend error:[/] {e}")
        raise typer.Exit(1)
    if require_fit:
        from .audit import audit_skill

        rep = audit_skill(skill, backend=be)
        if rep.verdict == "skip":
            ui.print(
                f"[red]Not a temper fit:[/] {'; '.join(rep.reasons)}  "
                "[dim](drop --require-fit to override)[/]"
            )
            raise typer.Exit(3)
        ui.print(
            f"[green]fitness: {rep.verdict}[/]"
            + (f"  ⚠ {'; '.join(rep.caveats)}" if rep.caveats else "")
        )
    if propose_schema:
        if schema:
            ui.print(
                "[red]--propose-schema and --schema are mutually exclusive[/] "
                "(--propose-schema drafts a schema; --schema pins one)."
            )
            raise typer.Exit(2)
        from .ingest import ingest_skill

        inferred = ingest_skill(skill, schema=None, backend=be, propose_schema_only=True)
        out_path = Path("schema.proposed.py")
        out_path.write_text(render_schema_source(inferred))
        _print_proposed_schema(ui, inferred, out_path, skill)
        if json_out:
            _emit_json(
                {
                    "proposed_schema_path": str(out_path),
                    "fn_name": inferred.fn_name,
                    "class": _classname(inferred.fn_name),
                    "features": [
                        {"name": f.name, "type": f.type, "description": f.description}
                        for f in inferred.features
                    ],
                    "constraints": list(inferred.constraints),
                }
            )
        raise typer.Exit(0)

    pinned = load_schema(schema) if schema else None
    ratified = load_dataset(examples) if examples else None
    out_p = Path(out)
    tree_path = str(out_p.parent / f"{out_p.stem}.py")

    def _checkpoint(t) -> None:  # write each round's tree so progress is followable + crash-safe
        try:
            t.export(tree_path)
        except OSError as e:
            ui.print(f"[yellow]checkpoint write failed ({e})[/]")

    ui.print(
        f"[cyan]Reading {skill}[/]  ·  backend: [bold]{be.describe()}[/]"
        + (f"  ·  schema: {schema}" if schema else "  ·  schema: inferred")
        + (f"  ·  {len(ratified)} ratified example(s)" if ratified else "")
        + f"  ·  [dim]writing each round → {tree_path}[/]"
    )
    confirm = (
        (lambda i: _confirm_schema(ui, i, auto=True))
        if (yes or json_out)
        else (lambda i: _confirm_schema(ui, i))
    )
    try:
        result = compile_tree(
            skill,
            be,
            out_dir=str(out_p.parent),
            stem=out_p.stem,
            profile=profile,
            schema=pinned,
            fn_name=fn,
            examples=ratified,
            propose_examples=propose_examples,
            gate=_make_gate(ui, interactive),
            confirm=confirm,
            checkpoint=_checkpoint,
            skill_style=skill_style,
            skill_out=skill_out,
        )
    except KeyboardInterrupt as e:
        ui.print(f"[red]Aborted:[/] {e}")
        raise typer.Exit(1)
    tree = result.tree
    cost = be.cost_estimate()
    cost_line = f"~${cost:.4f} (metered)" if cost is not None else "subscription — no metered cost"
    ui.print(Panel(tree.to_source(), title=f"Exported {result.tree_path}", border_style="green"))
    _print_loop_error(ui, tree)
    _print_example_check(ui, tree)
    _print_added_features(ui, tree)
    _print_schema_gaps(ui, tree)
    _print_outcome_gaps(ui, tree)
    if result.suite:
        _print_validation_panel(ui, result.suite)
    if result.weave_error:
        ui.print(
            f"[yellow]weave failed ({result.weave_error}); "
            "fell back to the deterministic template[/]"
        )
    _print_done(ui, result, skill_style, cost_line, be.describe())

    if json_out:
        manifest = tree_manifest(tree, result.tree_path, result.skill_path)
        manifest["backend"] = be.describe()
        manifest["cost_usd"] = cost
        _emit_json(manifest)


def _print_done(
    ui: Console, result: CompileResult, skill_style: str, cost_line: str, backend_desc: str
) -> None:
    """The closing summary leads with the test suite — the artifact most users came for;
    the tree is how it stays cheap (zero LLM calls at inference)."""
    done = []
    if result.suite:
        s = result.suite
        flag = f"  ·  [yellow]{s.disputes} open disagreement(s) to review[/]" if s.disputes else ""
        done.append(f"[green]✓[/] {s.cases}-case test suite → {s.test_path}{flag}")
        done.append(
            f"    [dim]labels are proposed, not ground truth — ratify them in {s.dataset_path}[/]"
        )
    done.append(
        f"[green]✓[/] deterministic tree → {result.tree_path}  "
        "[dim](zero LLM calls at inference)[/]"
    )
    if result.skill_path:
        module = Path(result.tree_path).with_suffix("").name
        done.append(
            f"[green]✓[/] tempered skill ({skill_style}) → {result.skill_path}  "
            f"[dim](delegates the decision to {module}.{result.tree.fn_name})[/]"
        )
    ui.print(Panel("\n".join(done), title="Done", border_style="green"))
    ui.print(f"[dim]backend {backend_desc} · cost: {cost_line}[/]")


def _print_added_features(ui: Console, tree) -> None:
    """Surface the co-evolved schema growth for the final review: features the schema_critic
    proposed that the loop ADDED and the tree then earned a branch on. Review before shipping —
    the schema is the caller's integration contract."""
    added = getattr(tree, "added_features", None)
    if not added:
        return
    lines = [
        "[green]The loop grew the schema — these features were added and earned a branch. "
        "Review them; they're now part of the caller's extraction contract:[/]"
    ]
    lines += [f"  • {a}" for a in added]
    ui.print(Panel("\n".join(lines), title="✎ schema grew (review)", border_style="green"))


def _print_schema_gaps(ui: Console, tree) -> None:
    """Surface the schema_critic's advisory findings: features the source needs but the
    schema can't express. The tree had to punt on these — consider re-opening the schema."""
    gaps = getattr(tree, "schema_gaps", None)
    if not gaps:
        return
    lines = [
        "[yellow]The schema_critic judged the schema too thin to fully express the "
        "source. The tree punts on these — consider adding them and re-running:[/]"
    ]
    lines += [f"  • {g}" for g in gaps]
    ui.print(Panel("\n".join(lines), title="✎ schema gaps (advisory)", border_style="yellow"))


def _print_outcome_gaps(ui: Console, tree) -> None:
    """Surface the outcome_critic's advisory findings: answers the source needs but the outcome
    vocabulary can't express, so two distinct answers collapse into one. Consider widening it."""
    gaps = getattr(tree, "outcome_gaps", None)
    if not gaps:
        return
    lines = [
        "[yellow]The outcome_critic judged the outcome set too coarse to express every "
        "answer the source calls for. Two distinct answers collapse into one — consider "
        "widening the outcome vocabulary and re-running:[/]"
    ]
    lines += [f"  • {g}" for g in gaps]
    ui.print(Panel("\n".join(lines), title="✎ outcome gaps (advisory)", border_style="yellow"))


def _print_loop_error(ui: Console, tree) -> None:
    """A run that ended on a backend failure must not read as a converged run."""
    err = getattr(tree, "loop_error", None)
    if err:
        ui.print(
            f"[yellow]⚠ the loop ended early on a backend failure ({err}) — "
            "the best tree so far was kept; consider re-running[/]"
        )


def _print_example_check(ui: Console, tree) -> None:
    """Surface the ratified-examples check (if any examples were provided)."""
    r = getattr(tree, "example_report", None)
    if r is None:
        return
    if not r.disagreements:
        ui.print(f"[green]✓ ratified examples: {r.agreements}/{r.total} agree[/]")
        return
    lines = [
        f"[red]{r.agreements}/{r.total} ratified examples agree[/] — "
        "each disagreement is a tree bug or a mislabeled example; sign off:"
    ]
    for d in r.disagreements:
        lines.append(f"  input={d.input}")
        lines.append(f"    expected [green]{d.expected}[/]  ·  got [red]{d.predicted}[/]")
    ui.print(
        Panel("\n".join(lines), title="⚠ ratified-example disagreements", border_style="yellow")
    )


def _print_proposed_schema(ui: Console, inferred: InferredSchema, path: Path, skill: str) -> None:
    """Surface the drafted contract + its normalization burden, awaiting ratification."""
    notes = normalization_notes(inferred)
    lines = [
        f"Decision function: [bold]{inferred.fn_name}[/]",
        f"Class: [bold]{_classname(inferred.fn_name)}[/]",
        "",
        "Fields:",
    ]
    for f in inferred.features:
        warn = f"   [yellow]⚠ {notes[f.name]}[/]" if f.name in notes else ""
        lines.append(f"  • {f.name}: {f.type}{warn}")
    if inferred.constraints:
        lines.append("\nInferred constraints (review, then pass via --constraint):")
        for c in inferred.constraints:
            lines.append(f"  • {c}  [hard]")
    if notes:
        lines.append(
            "\n[dim]The tree is only as safe as the normalizer feeding these "
            "exact-match fields. A Literal closes the space and helps the loop "
            "converge; a bare str reopens it.[/]"
        )
    cls = _classname(inferred.fn_name)
    lines.append(
        f"\n[bold]proposed labels, not ground truth.[/] Review/edit [bold]{path}[/], "
        f"then re-run to distill:\n  [bold]temper-skills ingest {skill} "
        f"--schema {path}:{cls}[/]"
    )
    ui.print(
        Panel(
            "\n".join(lines),
            title="✎ proposed schema (awaiting ratification)",
            border_style="magenta",
        )
    )


def _print_validation_panel(ui: Console, suite: SuiteResult) -> None:
    """Render the proposed validation dataset (already written by the pipeline)."""
    lines = [
        f"The loop drafted [bold]{suite.cases}[/] validation case(s) — [bold]proposed "
        'labels, not ground truth.[/] Review, fix any label, set [bold]"status": '
        '"ratified"[/], and re-run to anchor these cells. Disagreements are data (not '
        "failing tests):"
    ]
    for e in suite.enriched:
        flag = "  [yellow](differs from tree)[/]" if e["agrees"] is False else ""
        src = f" [dim]— {e['source']}[/]" if e.get("source") else ""
        lines.append(f"  input={e['input']}{src}")
        lines.append(
            f"    proposed [green]{e['expected']}[/]  ·  tree says [cyan]{e['tree_prediction']}[/]{flag}"
        )
        lines.append(f"    [dim]{e['rationale']}[/]")
    lines.append(
        f"\n[dim]dataset → {suite.dataset_path} · behavior-lock → "
        f"{suite.test_path} ({suite.disputes} open disagreement(s))[/]"
    )
    ui.print(
        Panel(
            "\n".join(lines),
            title="✎ validation dataset (awaiting ratification)",
            border_style="magenta",
        )
    )


@app.command()
def incremental(
    prior: str = typer.Argument(..., help="Prior tree.json to evolve."),
    skill: str = typer.Option(None, help="Updated skill.md to fold in (optional)."),
    constraint: list[str] = typer.Option(
        [], "--constraint", "-c", help="New HARD constraint (repeatable)."
    ),
    profile: str = typer.Option("standard", help=f"One of {list(PROFILES)}."),
    out: str = typer.Option("decision_tree.generated.py", help="Output .py path."),
    model: str = typer.Option(
        "claude-sonnet-4-6", help="Model: any LiteLLM id (claude-sonnet-4-6, openai/gpt-4o, …)."
    ),
    backend: str = typer.Option("auto", help="auto | api | claude | opencode."),
    fn: str = typer.Option(None, help="Override the function name."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Don't stop at each round."),
):
    """Re-crystallize an existing tree against new constraints/sources; show the diff."""
    ui = _console()
    prior_tree = tree_from_dict(_json.loads(Path(prior).read_text()))
    schema = {
        "type": "object",
        "properties": {f: {} for f in prior_tree.features},
        "additionalProperties": True,
    }
    sources = Sources(
        schema=schema,
        constraints=[{"rule": c, "hard": True} for c in constraint],
        skill_text=Path(skill).read_text() if skill else None,
    )
    try:
        be = get_backend(backend, model)
    except (ValueError, RuntimeError) as e:
        ui.print(f"[red]Backend error:[/] {e}")
        raise typer.Exit(1)
    interactive = PROFILES[profile][2] and not yes
    ui.print(
        f"[cyan]Evolving {prior}[/]  ·  backend: [bold]{be.describe()}[/]  "
        f"·  +{len(constraint)} constraint(s)"
    )
    try:
        new_tree, diff = recrystallize(
            prior_tree,
            sources,
            profile=profile,
            backend=be,
            gate=_make_gate(ui, interactive),
            fn_name=fn,
        )
    except KeyboardInterrupt as e:
        ui.print(f"[red]Aborted:[/] {e}")
        raise typer.Exit(1)
    new_tree.export(out)
    title = "no change" if diff.is_empty else "structural diff (v_n → v_n+1)"
    ui.print(Panel(render_diff(diff), title=title, border_style="magenta"))
    ui.print(Panel(new_tree.to_source(), title=f"Exported {out}", border_style="green"))


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
    ui = _console()
    if match not in COMPARATORS:
        ui.print(f"[red]--match must be one of {list(COMPARATORS)}[/]")
        raise typer.Exit(2)
    decide = fn_from_pyfile(artifact, fn) if artifact.endswith(".py") else fn_from_json(artifact)
    report = run_validation(decide, load_dataset(dataset), COMPARATORS[match])

    pct = report.agreement_rate * 100
    color = "green" if report.passed(min_agreement) else "red"
    lines = [f"Passed: [{color}]{report.agreements}/{report.total} case(s) ({pct:.1f}%)[/]"]
    if report.disagreements:
        lines.append("\n[bold]Failures[/] — each is a tree bug or a mislabeled case; sign off:")
        for d in report.disagreements:
            lines.append(f"  input={d.input}")
            lines.append(f"    expected [green]{d.expected}[/]  ·  got [red]{d.predicted}[/]")
    ui.print(Panel("\n".join(lines), title=f"test run — {artifact}", border_style=color))
    if not report.passed(min_agreement):
        raise typer.Exit(1)


@app.command()
def audit(
    skill: str = typer.Argument(
        ..., help="A skill.md to audit — or a DIRECTORY to sweep as a library."
    ),
    model: str = typer.Option("claude-sonnet-4-6", help="Model: any LiteLLM id."),
    backend: str = typer.Option("auto", help="LLM backend: auto | api | claude | opencode."),
    profile: str = typer.Option(
        "standard", help=f"Temper profile if you follow the action: {list(PROFILES)}."
    ),
    out_dir: str = typer.Option(".", help="Where to write trees/skill if you follow the action."),
    report_md: str = typer.Option(
        None, "--report", help="Also write the findings as a Markdown report (pasteable in a PR)."
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emit the FitnessReport(s) as JSON (for a pipeline / the Evolve Server).",
    ),
):
    """Find out what a skill is silently deciding — and what to do about it.

    Point it at one skill.md for a findings report, or at a directory to audit the
    whole library (one cheap judge turn per skill, in parallel), ranked by what's most
    worth acting on. Exits 0 when anything is actionable, 3 when everything is a skip —
    so a pipeline can triage a library and only crystallize the fits.
    """
    from .audit import audit_skill

    ui = _console(json_out)  # stdout must carry ONLY the machine-readable report(s)
    try:
        be = get_backend(backend, model)
    except (ValueError, RuntimeError) as e:
        ui.print(f"[red]Backend error:[/] {e}")
        raise typer.Exit(1)

    if Path(skill).is_dir():
        _audit_library(ui, skill, be, json_out=json_out, report_md=report_md)
        return

    report = audit_skill(skill, backend=be)
    if report_md:
        from .audit_report import render_audit_md

        Path(report_md).write_text(render_audit_md(report, skill))
        ui.print(f"[dim]report → {report_md}[/]")
    if json_out:
        _emit_json(_json.loads(report.model_dump_json()))
        if report.verdict == "skip":
            raise typer.Exit(3)
        return

    _print_fitness(ui, report, skill)
    action = report.recommended_action
    # Continuity: offer to follow the Next action right here (the threaded press-[1]).
    if ui.is_terminal and action in ("temper", "decompose"):
        if (
            Prompt.ask(
                f"[bold]1[/] run `{action}` now · [bold]2[/] just the audit",
                choices=["1", "2"],
                default="2",
            )
            == "1"
        ):
            if action == "decompose":
                _decompose_pipeline(
                    ui,
                    skill,
                    be,
                    out_dir,
                    profile,
                    temper_each=True,
                    yes_unratified=False,
                    emit_schemas=False,
                    json_out=False,
                )
            else:
                _temper_pipeline(ui, skill, be, out_dir, profile)
            return
    if report.verdict == "skip":
        raise typer.Exit(3)


_HEADLINE_COLOR = {"temper": "green", "caveats": "yellow", "skip": "red"}


def _audit_library(ui: Console, root: str, be, *, json_out: bool, report_md: str | None) -> None:
    """The library sweep: rank every skill under ``root`` by what's most worth acting on."""
    from .audit_report import audit_library, headline_of, render_library_md, top_finding

    rows = audit_library(root, be)
    if not rows:
        ui.print(
            f"[red]no skills found under {root}[/] "
            "[dim](looked for SKILL.md files, then any non-furniture .md)[/]"
        )
        raise typer.Exit(2)

    if json_out:
        _emit_json(
            [
                {
                    "path": str(r.path),
                    **(
                        {"error": r.error}
                        if r.report is None
                        else _json.loads(r.report.model_dump_json())
                    ),
                }
                for r in rows
            ]
        )
    else:
        from rich.table import Table

        table = Table(
            title=f"Skill library audit — {root} ({len(rows)} skill(s))",
            border_style="cyan",
            show_lines=False,
            pad_edge=False,
        )
        table.add_column("skill", style="bold", overflow="fold")
        table.add_column("verdict")
        table.add_column("top finding", overflow="fold")
        table.add_column("fix", style="dim")
        for row in rows:
            rel = row.path.relative_to(root) if row.path.is_relative_to(Path(root)) else row.path
            if row.report is None:
                table.add_row(str(rel), "[red]audit failed[/]", row.error or "", "—")
                continue
            r = row.report
            label, _ = headline_of(r)
            color = "cyan" if r.recommended_action == "decompose" else _HEADLINE_COLOR[r.verdict]
            table.add_row(str(rel), f"[{color}]{label}[/]", top_finding(r), r.recommended_action)
        ui.print(table)
        ui.print(
            "[dim]details per skill: temper-skills audit <path>  ·  "
            "shareable report: --report audit.md[/]"
        )

    if report_md:
        Path(report_md).write_text(render_library_md(rows, root))
        ui.print(f"[dim]report → {report_md}[/]")
    if all(r.report is None or r.report.verdict == "skip" for r in rows):
        raise typer.Exit(3)


def _print_fitness(ui: Console, report, skill: str) -> None:
    """Findings for the skill's AUTHOR — what it silently decides and what to do about
    it — not a gate verdict for the temper pipeline (audit_report owns the wording)."""
    from .audit_report import findings_of, headline_of

    label, gloss = headline_of(report)
    color = "cyan" if report.recommended_action == "decompose" else _HEADLINE_COLOR[report.verdict]
    body = [
        f"[{color}][bold]{label}[/] — {gloss}[/]",
        f"decision: [bold]{report.fn_name}[/]   ·   {skill}",
    ]

    said = [(a, report.rationale.get(a)) for a in ("decisiveness", "combinatorics", "stakes")]
    if any(why for _, why in said):
        body += ["", "[bold]What this skill is deciding[/]"]
        body += [f"  [dim]{axis}:[/] {why}" for axis, why in said if why]

    body += ["", "[bold]Findings[/]"]
    for f in findings_of(report):
        mark = "[green]✓[/]" if f.severity == "good" else "[yellow]⚠[/]"
        body.append(f"  {mark} {f.text}")
        body.append(f"       [dim]fix: {f.fix}[/]")

    if report.action_hint:
        body += [
            "",
            f"[bold]Recommended: {report.recommended_action.upper()}[/] — {report.action_hint}",
        ]
    body += [
        "",
        f"[dim]scores: decisiveness {report.decisiveness}/10 · interactions "
        f"{report.combinatorics}/10 · stakes {report.stakes}/10 · bounded inputs "
        f"{report.schema_closure:.0%} of {report.n_features} feature(s)[/]",
    ]
    ui.print(Panel("\n".join(body), title="Skill audit", border_style=color))


def _plan_body(decomp, coup, reports) -> str:
    """The decomposition plan panel. With ``reports`` (audited) shows each verdict/action;
    without (we're about to temper anyway) shows the decision's outcomes instead."""
    vcolor = {"temper": "green", "caveats": "yellow", "skip": "red"}
    n = len(decomp.decisions)
    body = [f"[bold]{n} decision(s) + {len(decomp.generative_steps)} generative step(s)[/]", ""]
    for d in decomp.decisions:
        chain = "" if coup[d.fn_name] == "independent" else f"  ·  chain: {coup[d.fn_name]}"
        if reports:
            r = reports[d.fn_name]
            body.append(
                f"  [bold]{d.fn_name}[/]  [{vcolor[r.verdict]}]audit: {r.verdict.upper()}[/]"
                f"  ·  → {r.recommended_action}{chain}"
            )
        else:
            body.append(f"  [bold]{d.fn_name}[/]  →  {' / '.join(d.outcomes)}{chain}")
        body.append(f"      [dim]{d.description}[/]")
    for g in decomp.generative_steps:
        body.append(f"  [dim]generative:[/] {g}  [dim](left to the model)[/]")
    body += ["", f"[bold]Plan:[/] {n} tree(s) + an orchestrator skill that chains them"]
    return "\n".join(body)


def _decompose_pipeline(
    ui: Console,
    skill,
    be,
    out_dir,
    profile,
    *,
    temper_each,
    yes_unratified,
    emit_schemas,
    json_out,
    interactive=True,
):
    """The decompose flow, shared by the `decompose` command and `guide`. Returns the path
    to the orchestrator skill if it compiled, else None (plan-only or stopped to ratify)."""
    from .decompose import audit_decision, coupling, decompose_skill, Decomposition, InferredSchema
    from .export_skill import render_orchestrator_skill

    out = Path(out_dir)
    # Reuse a persisted plan so re-running --temper-each after ratifying doesn't re-decompose
    # (another LLM call) or drift the fn_names the ratified schemas are keyed to.
    plan_json = out / "decomposition.json"
    if (emit_schemas or temper_each) and plan_json.exists():
        decomp = Decomposition.model_validate_json(plan_json.read_text())
    else:
        decomp = decompose_skill(skill, backend=be)
    coup = coupling(decomp)

    fresh: list[str] = []
    if emit_schemas or temper_each:
        out.mkdir(parents=True, exist_ok=True)
        plan_json.write_text(decomp.model_dump_json(indent=2))
        for d in decomp.decisions:
            p = out / f"{d.fn_name}.schema.py"
            if not p.exists():
                p.write_text(
                    render_schema_source(InferredSchema(fn_name=d.fn_name, features=d.features))
                )
                fresh.append(d.fn_name)

    run = temper_each and (not fresh or yes_unratified)

    # Always show the decomposition plan — audit each decision only when we're NOT about to
    # temper (the per-decision audit is N extra LLM calls; pointless right before the loops).
    reports = {} if run else {d.fn_name: audit_decision(d, be) for d in decomp.decisions}
    if not run and json_out:
        _emit_json(
            {
                "decomposition": _json.loads(decomp.model_dump_json()),
                "audits": {k: _json.loads(r.model_dump_json()) for k, r in reports.items()},
            }
        )
    elif not json_out:
        ui.print(
            Panel(
                _plan_body(decomp, coup, reports), title="Skill decomposition", border_style="cyan"
            )
        )

    if not run:
        if temper_each and fresh:
            ui.print(
                f"\n[yellow]Emitted {len(fresh)} schema(s) to {out}/ — ratify them "
                "(tighten free-text str → Literal) so the open-text actions become "
                "`temper`.[/]"
            )
            if interactive and ui.is_terminal and not json_out:
                if (
                    Prompt.ask(
                        "Next  [bold]1[/] temper each now (on these unratified schemas) · "
                        "[bold]2[/] stop — I'll ratify first",
                        choices=["1", "2"],
                        default="2",
                    )
                    == "1"
                ):
                    run = True
            if not run:
                ui.print(
                    f"[dim]when ready: temper-skills decompose {skill} --temper-each "
                    f"--out-dir {out}  (re-run reuses your ratified schemas)[/]"
                )
        elif emit_schemas:
            for fn in fresh:
                ui.print(f"[green]wrote[/] {out / f'{fn}.schema.py'}")
    if not run:
        return None

    original = Path(skill).read_text()
    items = []
    for d in decomp.decisions:
        schema_path = f"{out / f'{d.fn_name}.schema.py'}:{_classname(d.fn_name)}"
        ui.rule(f"[cyan]tempering {d.fn_name}[/]")
        res = compile_tree(
            skill,
            be,
            out_dir=str(out),
            stem=d.fn_name,
            profile=profile,
            schema=load_schema(schema_path),
            fn_name=d.fn_name,
            gate=_make_gate(ui, False),
            propose_examples=True,
            skill_style=None,
        )  # the orchestrator below stitches the flow
        _print_loop_error(ui, res.tree)
        if res.suite:
            _print_validation_panel(ui, res.suite)
        items.append(
            {
                "fn": d.fn_name,
                "module": d.fn_name,
                "features": res.tree.features,
                "consumes": d.consumes,
                "gray_zones": [n.gray_zone for n in res.tree.nodes if n.gray_zone],
            }
        )

    sp = Path(skill)
    name = sp.parent.parent.name if sp.parent.name == "input" else sp.stem
    md = render_orchestrator_skill(name, items, decomp.generative_steps, original)
    orch = out / f"{name}.tempered.md"
    orch.write_text(md)
    ui.print(
        Panel(
            f"{len(items)} tree(s) → {out}/\norchestrator → {orch}",
            title="Tempered the flow",
            border_style="green",
        )
    )
    return orch


def _temper_pipeline(ui: Console, skill, be, out_dir, profile, *, schema_spec=None, fn=None):
    """Freeze a single decision: run the loop, write the tree + a tempered skill. Returns
    the path to the tempered skill.md."""
    pinned = load_schema(schema_spec) if schema_spec else None
    res = compile_tree(
        skill,
        be,
        out_dir=out_dir,
        profile=profile,
        schema=pinned,
        fn_name=fn,
        gate=_make_gate(ui, False),
        confirm=lambda i: True,
        propose_examples=True,
    )
    _print_loop_error(ui, res.tree)
    if res.suite:
        _print_validation_panel(ui, res.suite)
    ui.print(
        Panel(
            f"tree → {res.tree_path}\ntempered skill → {res.skill_path}",
            title="Tempered the decision",
            border_style="green",
        )
    )
    assert res.skill_path is not None  # skill_style defaults to "template" on this path
    return Path(res.skill_path)


@app.command()
def decompose(
    skill: str = typer.Argument(
        ..., help="Path to a big skill.md (a flow) to split into decisions."
    ),
    model: str = typer.Option("claude-sonnet-4-6", help="Model: any LiteLLM id."),
    backend: str = typer.Option("auto", help="LLM backend: auto | api | claude | opencode."),
    emit_schemas: bool = typer.Option(
        False,
        "--emit-schemas",
        help="Write a per-decision mini-schema (<fn>.schema.py) you can ratify then `ingest`.",
    ),
    temper_each: bool = typer.Option(
        False,
        "--temper-each",
        help="Run the whole plan: emit a schema per decision and STOP for ratification; once "
        "ratified, re-run to temper each into a tree + emit the orchestrator skill.",
    ),
    yes_unratified: bool = typer.Option(
        False,
        "--yes-unratified",
        help="With --temper-each: don't stop — temper now on the raw inferred schemas.",
    ),
    profile: str = typer.Option(
        "standard", help=f"Temper profile for --temper-each: {list(PROFILES)}."
    ),
    out_dir: str = typer.Option(
        ".", help="Where schemas, trees, and the orchestrator are written."
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit the Decomposition + per-decision audits as JSON."
    ),
):
    """Split a flow-shaped skill into its decision points, audit each, and (optionally) temper them."""
    ui = _console(json_out)
    try:
        be = get_backend(backend, model)
    except (ValueError, RuntimeError) as e:
        ui.print(f"[red]Backend error:[/] {e}")
        raise typer.Exit(1)
    _decompose_pipeline(
        ui,
        skill,
        be,
        out_dir,
        profile,
        temper_each=temper_each,
        yes_unratified=yes_unratified,
        emit_schemas=emit_schemas,
        json_out=json_out,
    )


@app.command()
def guide(
    skill: str = typer.Argument(
        ..., help="Path to a skill.md to drive end-to-end, press-[1] style."
    ),
    model: str = typer.Option("claude-sonnet-4-6", help="Model: any LiteLLM id."),
    backend: str = typer.Option("auto", help="LLM backend: auto | api | claude | opencode."),
    profile: str = typer.Option(
        "quick", help=f"Temper profile (quick keeps the demo short): {list(PROFILES)}."
    ),
    out_dir: str = typer.Option(".", help="Where trees and the (orchestrator) skill are written."),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emit a machine-readable manifest to stdout (audit verdict, action taken, status, "
        "artifact paths); human panels go to stderr. For agents/pipelines driving the CLI.",
    ),
):
    """Guided demo: audit a skill, follow the recommended action with a few [1]s, and end with
    a full generated skill. The one-command tour of the whole pipeline."""
    from .audit import audit_skill

    ui = _console(json_out)
    try:
        be = get_backend(backend, model)
    except (ValueError, RuntimeError) as e:
        ui.print(f"[red]Backend error:[/] {e}")
        raise typer.Exit(1)

    ui.rule("[bold]1 — audit[/]")
    report = audit_skill(skill, backend=be)
    _print_fitness(ui, report, skill)
    audit_dump = _json.loads(report.model_dump_json())
    if ui.is_terminal and not json_out:
        if (
            Prompt.ask(
                "[bold]1[/] follow the recommendation · [bold]2[/] quit",
                choices=["1", "2"],
                default="1",
            )
            != "1"
        ):
            raise typer.Exit(0)

    def _guide_manifest(action: str, final, status: str) -> dict:
        return {
            "command": "guide",
            "skill": skill,
            "audit": audit_dump,
            "action_taken": action,
            "status": status,
            "out_dir": out_dir,
            "final_skill_path": str(final) if final else None,
            "artifacts": sorted(str(p) for p in Path(out_dir).glob("*") if p.is_file()),
        }

    action = report.recommended_action
    final = None
    if action == "decompose":
        ui.rule("[bold]2 — decompose → temper each[/]")
        final = _decompose_pipeline(
            ui,
            skill,
            be,
            out_dir,
            profile,
            temper_each=True,
            yes_unratified=False,
            emit_schemas=False,
            json_out=False,
        )
    elif action == "temper":
        ui.rule("[bold]2 — temper[/]")
        final = _temper_pipeline(ui, skill, be, out_dir, profile)
    else:
        ui.print(f"\n[yellow]Recommended action: {action}[/] — {report.action_hint}")
        ui.print("[dim]This action isn't auto-run by the guide (see the hint above).[/]")
        if json_out:
            _emit_json(_guide_manifest(action, None, "action_not_auto_run"))
        raise typer.Exit(0)

    if final is None:
        # decompose stopped for ratification — re-run guide after ratifying
        if json_out:
            _emit_json(_guide_manifest(action, None, "stopped_for_ratification"))
        raise typer.Exit(0)
    ui.rule("[bold green]✓ full skill[/]")
    ui.print(Panel(final.read_text(), title=str(final), border_style="green"))
    if json_out:
        _emit_json(_guide_manifest(action, final, "compiled"))


def _implicit_command(arg: str) -> str | None:
    """Bare invocation: `temper-skills <dir>` sweeps the library, `temper-skills <file>`
    runs the guided tour — one thing to remember instead of five subcommands. Explicit
    subcommand names and flags always win."""
    names = {
        (c.name or (c.callback.__name__ if c.callback else "")).replace("_", "-")
        for c in app.registered_commands
    }
    if arg.startswith("-") or arg in names:
        return None
    p = Path(arg)
    if not p.exists():
        return None
    return "audit" if p.is_dir() else "guide"


def main() -> None:
    """Console-script entry: resolve a bare path to its implicit command, then dispatch."""
    import sys

    if len(sys.argv) > 1:
        implicit = _implicit_command(sys.argv[1])
        if implicit:
            sys.argv.insert(1, implicit)
    app()


if __name__ == "__main__":
    main()
