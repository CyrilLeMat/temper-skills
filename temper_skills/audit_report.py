"""The audit as an author-facing report — findings + fixes, not a gate verdict.

``audit.py`` owns the scoring (pinned by test_audit, untouched here). This module turns
a FitnessReport into what a skill *author* needs to read: what their skill is silently
deciding, findings about it, and a fix per finding — with tempering as one recommended
fix, not the premise. Findings derive from the report's FIELDS (never by parsing the
caveat strings), so wording here can evolve without touching the pinned rubric.

Kept free of Rich/typer so a pipeline or CI step (the future GitHub Action) can import
it: Markdown rendering for PR comments, and the library fan-out behind
``temper-skills audit <dir>``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .audit import FitnessReport, audit_skill
from .backends import Backend


@dataclass
class Finding:
    severity: str  # "warn" | "good"
    text: str      # what the audit observed, in skill-author words
    fix: str       # what to do about it


def findings_of(r: FitnessReport) -> list[Finding]:
    out: list[Finding] = []
    if r.distinct_decisions >= 2:
        out.append(Finding(
            "warn",
            f"bundles ~{r.distinct_decisions} separable decisions — every score below "
            "averages them",
            "split first (`temper-skills decompose`); each decision gets its own tree "
            "+ test suite",
        ))
    if r.decisiveness < 4:
        out.append(Finding(
            "warn",
            "no finite decision to freeze — this skill is mostly open-ended generation",
            "improve it as prose (e.g. skill-creator); there is nothing to compile here",
        ))
    if r.open_features:
        names = ", ".join(f"`{n}`" for n in r.open_features)
        if r.recommended_action == "externalize_data":
            fix = ("move the lookup into a versioned data file + matcher; freeze only "
                   "the residual logic")
        elif r.recommended_action == "build_normalizer":
            fix = ("pin these fields to canonical values upstream (your extractor) "
                   "before freezing")
        else:
            fix = ("tighten each to a closed set (a `Literal`) or own the mapping in "
                   "your normalizer")
        out.append(Finding(
            "warn",
            f"branches on free text with an unbounded value space: {names} — answers "
            "can drift call-to-call",
            fix,
        ))
    if r.decisiveness >= 4 and r.combinatorics <= 5:
        out.append(Finding(
            "warn",
            "the difficulty reads as item-by-item lookup, not interacting rules",
            "keep the list as data; only genuine feature interactions belong in code",
        ))
    if r.n_features <= 1:
        out.append(Finding(
            "warn",
            "only one input feature — the \"logic\" may be a plain lookup table",
            "confirm there are real branches; a dict may serve better than a tree",
        ))
    if r.stakes < 4:
        out.append(Finding(
            "warn",
            "low-stakes or fast-changing — freezing may not pay for itself",
            "temper only if this decision repeats enough to earn its maintenance",
        ))
    if not out:
        out.append(Finding(
            "good",
            "decisive, interacting, bounded inputs — a prime candidate for freezing",
            "`temper-skills ingest <skill>` → deterministic code + a reviewed test suite",
        ))
    return out


def headline_of(r: FitnessReport) -> tuple[str, str]:
    """Author-facing verdict label + gloss (the CLI adds color, Markdown adds bold)."""
    if r.recommended_action == "decompose":
        return ("SPLIT FIRST",
                f"a flow of ~{r.distinct_decisions} decisions — decompose, then freeze each")
    return {
        "temper":  ("FREEZE-WORTHY",
                    "decision logic worth compiling into code + a test suite"),
        "caveats": ("FREEZE-WORTHY, WITH FINDINGS",
                    "compilable — read the findings first"),
        "skip":    ("NOTHING TO FREEZE",
                    "don't grow a tree here — see the findings"),
    }[r.verdict]


def _scores_line(r: FitnessReport) -> str:
    return (f"scores: decisiveness {r.decisiveness}/10 · interactions "
            f"{r.combinatorics}/10 · stakes {r.stakes}/10 · bounded inputs "
            f"{r.schema_closure:.0%} of {r.n_features} feature(s)")


def render_audit_md(r: FitnessReport, skill: str) -> str:
    """One skill's findings as Markdown — pasteable in a PR comment."""
    label, gloss = headline_of(r)
    lines = [
        f"# Skill audit — `{Path(skill).name}`",
        "",
        f"**{label}** — {gloss}",
        "",
        f"Decision: `{r.fn_name}` · source: `{skill}`",
        "",
        "## Findings",
        "",
    ]
    for f in findings_of(r):
        mark = "✅" if f.severity == "good" else "⚠️"
        lines.append(f"- {mark} {f.text}")
        lines.append(f"  - **fix:** {f.fix}")
    for axis in ("decisiveness", "combinatorics", "stakes"):
        why = r.rationale.get(axis)
        if why:
            lines += ["", f"> *{axis}*: {why}"]
    lines += [
        "",
        f"**Recommended action:** `{r.recommended_action}` — {r.action_hint}",
        "",
        f"<sub>{_scores_line(r)}</sub>",
        "",
    ]
    return "\n".join(lines)


# ---- library fan-out: `temper-skills audit <dir>` ----

@dataclass
class LibraryRow:
    path: Path
    report: FitnessReport | None = None
    error: str | None = None


_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}
_REPO_FURNITURE = {"readme.md", "changelog.md", "contributing.md", "license.md",
                   "claude.md", "agents.md", "plan.md"}


def discover_skills(root: Path) -> list[Path]:
    """``SKILL.md`` files if the library uses that convention (``.claude/skills/``,
    exported skill dirs); otherwise every ``.md`` that isn't repo furniture or an
    already-tempered output."""
    def walk(keep):
        return sorted(
            p for p in root.rglob("*.md")
            if not any(part in _SKIP_DIRS for part in p.parts) and keep(p)
        )
    named = walk(lambda p: p.name.lower() == "skill.md")
    if named:
        return named
    return walk(lambda p: p.name.lower() not in _REPO_FURNITURE
                and not p.name.endswith(".tempered.md"))


def rank_key(row: LibraryRow) -> tuple:
    """Most worth acting on first: actionable verdicts, then decisiveness × stakes.
    Skips sink; audit errors sink below them."""
    if row.report is None:
        return (2, 0)
    r = row.report
    return (0 if r.verdict != "skip" else 1, -(r.decisiveness * r.stakes))


def audit_library(root: str | Path, backend: Backend, max_workers: int = 8) -> list[LibraryRow]:
    """Audit every skill under ``root`` (one judge turn each, in parallel) and rank."""
    paths = discover_skills(Path(root))

    def one(p: Path) -> LibraryRow:
        try:
            return LibraryRow(p, report=audit_skill(str(p), backend=backend))
        except Exception as e:  # one bad skill must not sink the library sweep
            return LibraryRow(p, error=str(e))

    if not paths:
        return []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(paths))) as ex:
        rows = list(ex.map(one, paths))
    return sorted(rows, key=rank_key)


def top_finding(r: FitnessReport) -> str:
    return findings_of(r)[0].text


def render_library_md(rows: list[LibraryRow], root: str | Path) -> str:
    """The library sweep as a Markdown table — the shareable 'I audited N skills' artifact."""
    lines = [
        f"# Skill library audit — `{root}`",
        "",
        f"{len(rows)} skill(s) audited, ranked by what's most worth acting on.",
        "",
        "| skill | verdict | decisions | top finding | fix |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        rel = row.path.relative_to(root) if row.path.is_relative_to(Path(root)) else row.path
        if row.report is None:
            lines.append(f"| `{rel}` | audit failed | — | {row.error} | — |")
            continue
        r = row.report
        label, _ = headline_of(r)
        lines.append(f"| `{rel}` | {label} | {r.distinct_decisions} | "
                     f"{top_finding(r)} | `{r.recommended_action}` |")
    lines.append("")
    return "\n".join(lines)
