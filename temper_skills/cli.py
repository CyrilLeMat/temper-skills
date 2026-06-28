"""Interactive CLI — the loop is not a black box; the user sees each round (§4.3)."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .backends import get_backend
from .distill import PROFILES, RoundResult
from .ingest import InferredSchema, ingest_skill
from .validate import COMPARATORS, fn_from_json, fn_from_pyfile, load_dataset, run_validation

app = typer.Typer(add_completion=False, help="Temper-Skills: prompt logic -> deterministic code.")
console = Console()


@app.callback()
def _main() -> None:
    """Temper-Skills CLI. See `ingest`."""

_VERDICT_MARK = {"ok": "[green]✓[/]", "missing_case": "[yellow]⚠[/]",
                 "collapsible": "[yellow]⚠[/]", "contradiction": "[red]✗[/]"}


def _confirm_schema(inferred: InferredSchema) -> bool:
    lines = [f"Decision function: [bold]{inferred.fn_name}[/]", "", "Inferred schema:"]
    for f in inferred.features:
        desc = f"  — {f.description}" if f.description else ""
        lines.append(f"  • {f.name}: {f.type}{desc}")
    if inferred.constraints:
        lines.append("\nInferred constraints:")
        for c in inferred.constraints:
            lines.append(f"  • {c}  [hard]")
    console.print(Panel("\n".join(lines), title="Inferred from skill", border_style="cyan"))
    return Prompt.ask("Accept schema?", choices=["y", "n"], default="y") == "y"


def _make_gate(interactive: bool):
    def gate(r: RoundResult) -> str:
        body = [
            f"[bold]Round {r.round}/{r.max_rounds}[/]   "
            f"convergence estimate: {r.arbitration.convergence_estimate}%   "
            f"scores: min {r.min_score}/10, mean {r.mean_score}/10",
            "",
            "Persona scores & verdicts:",
        ]
        for v in sorted(r.verdicts, key=lambda x: x.score):
            mark = _VERDICT_MARK.get(v.verdict, "•")
            body.append(f"  {mark} [bold]{v.persona}[/]  [bold]{v.score}/10[/]  — {v.detail}")
        body.append("\nProposer arbitrage log:")
        for e in r.arbitration.entries:
            body.append(f"  [{e.decision}] {e.persona}: {e.rationale}")
        body.append("\nCurrent tree:")
        for i, n in enumerate(r.tree.nodes, 1):
            body.append(f"  n{i}: if ({n.condition}) -> {n.outcome}")
        body.append(f"  default -> {r.tree.default_outcome}")
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
    model: str = typer.Option("claude-sonnet-4-6", help="Compile-time model."),
    backend: str = typer.Option(
        "auto", help="LLM backend: auto | api | claude | opencode."
    ),
):
    """Compile a skill's decision logic into a deterministic Python tree."""
    interactive = PROFILES[profile][2]
    try:
        be = get_backend(backend, model)
    except (ValueError, RuntimeError) as e:
        console.print(f"[red]Backend error:[/] {e}")
        raise typer.Exit(1)
    console.print(f"[cyan]Reading {skill}[/]  ·  backend: [bold]{be.describe()}[/]")
    try:
        tree = ingest_skill(
            skill, schema=None, profile=profile, backend=be,
            gate=_make_gate(interactive), confirm=_confirm_schema,
        )
    except KeyboardInterrupt as e:
        console.print(f"[red]Aborted:[/] {e}")
        raise typer.Exit(1)
    tree.export(out)
    cost = be.cost_estimate()
    cost_line = f"~${cost:.4f} (metered)" if cost is not None else "subscription — no metered cost"
    console.print(Panel(tree.to_source(), title=f"Exported {out}", border_style="green"))
    console.print(f"[dim]backend {be.describe()} · cost: {cost_line}[/]")


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


if __name__ == "__main__":
    app()
