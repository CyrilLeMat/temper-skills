"""Interactive CLI — the loop is not a black box; the user sees each round (§4.3)."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .distill import PROFILES, RoundResult
from .ingest import InferredSchema, ingest_skill

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
):
    """Compile a skill's decision logic into a deterministic Python tree."""
    interactive = PROFILES[profile][2]
    console.print(f"[cyan]Reading {skill}…[/]")
    try:
        tree = ingest_skill(
            skill, schema=None, profile=profile, model=model,
            gate=_make_gate(interactive), confirm=_confirm_schema,
        )
    except KeyboardInterrupt as e:
        console.print(f"[red]Aborted:[/] {e}")
        raise typer.Exit(1)
    tree.export(out)
    console.print(Panel(tree.to_source(), title=f"Exported {out}", border_style="green"))


if __name__ == "__main__":
    app()
