"""Single source of truth for the skill docs' parameter tables.

The personas, profiles, and convergence rule live in code (``sources.py`` /
``distill.py``). The skill markdown re-states them for the agent, which is where they
silently drift. Instead of hand-maintaining those tables, the docs carry marked regions

    <!-- BEGIN GENERATED:profiles -->
    ...rendered from code...
    <!-- END GENERATED:profiles -->

that this module fills. ``sync()`` rewrites them; ``sync(check=True)`` reports any doc
whose committed region differs from a fresh render (the CI guard — see
``tests/test_skill_docs_sync.py``). Edit the code, run ``python -m temper_skills.skill_docs``.
"""

from __future__ import annotations

import re
from pathlib import Path

from .distill import _EARN_ROUNDS, HARVEST_EXCLUDED, PROFILE_PERSONAS, PROFILES
from .sources import DEFAULT_PERSONAS, OUTCOME_CRITIC, OVERENGINEERING_CRITIC, SCHEMA_CRITIC
from .validation_case import STATUSES

_REPO_ROOT = Path(__file__).resolve().parents[1]

DOCS = [
    _REPO_ROOT / ".claude/skills/temper-skills/SKILL.md",
    _REPO_ROOT / "skills/temper-skills/references/profiles.md",
]

_EDIT_HINT = "_Generated from `temper_skills/{src}` — edit there, then run `python -m temper_skills.skill_docs`._"


def _render_personas() -> str:
    rows = [
        "| persona | always-on | angle (the `style` the model is given) |",
        "|---|---|---|",
    ]
    for p in DEFAULT_PERSONAS:
        rows.append(f"| `{p.name}` | — | {p.style} |")
    c = OVERENGINEERING_CRITIC
    rows.append(f"| `{c.name}` | ✅ every round | {c.style} |")
    sc = SCHEMA_CRITIC
    rows.append(f"| `{sc.name}` | ✅ standard & audit-grade | {sc.style} |")
    oc = OUTCOME_CRITIC
    rows.append(f"| `{oc.name}` | ✅ standard & audit-grade | {oc.style} |")
    return _EDIT_HINT.format(src="sources.py") + "\n\n" + "\n".join(rows)


def _panel(profile: str) -> str:
    names = [f"`{p.name}`" for p in PROFILE_PERSONAS[profile]]
    return ", ".join(names) + f", `{OVERENGINEERING_CRITIC.name}`"


def _render_profiles() -> str:
    rows = [
        "| profile | max rounds | stop after N quiet rounds | per-round gate | provenance comments | adversary panel |",
        "|---|---|---|---|---|---|",
    ]
    for name, (max_rounds, stop_quiet, interactive, provenance) in PROFILES.items():
        rows.append(
            f"| `{name}` | {max_rounds} | {stop_quiet} | "
            f"{'on' if interactive else 'off'} | {'on' if provenance else 'off'} | {_panel(name)} |"
        )
    return _EDIT_HINT.format(src="distill.py") + "\n\n" + "\n".join(rows)


def _render_convergence() -> str:
    return (
        _EDIT_HINT.format(src="distill.py")
        + "\n\n"
        + "The loop stops when **no round improves on the best for `stop after N quiet rounds` "
        "consecutive rounds** (a plateau — whether high, a good tree, or low, can't improve), "
        "or the round cap is hit, or the user stops. The per-profile `N` and cap are in the "
        "profile table above. Convergence is a *plateau*, not an absolute score threshold."
    )


def _render_loop_invariants() -> str:
    """The loop's fact card: the numbers/sets the surrounding prose narrates. The prose
    may paraphrase them (test_skill_prose_sync pins that); this block IS them."""
    excluded = ", ".join(f"`{n}`" for n in HARVEST_EXCLUDED)
    statuses = " → ".join(f"`{s}`" for s in STATUSES)
    return (
        _EDIT_HINT.format(src="distill.py / validation_case.py")
        + "\n\n"
        + f"- **earn-a-branch window:** an added feature/outcome must earn a surviving "
        f"branch within **{_EARN_ROUNDS} rounds** or be reverted to an advisory gap.\n"
        + f"- **case harvest excludes:** {excluded} — the structural critics restructure; "
        "they don't add cases.\n"
        + f"- **case statuses:** {statuses} — only a human-set `ratified` gates anything.\n"
        + "- **the only mid-run gate:** Continue · Stop and review · Abort. Everything "
        "else is decided, recorded, and reviewed at the end."
    )


RENDERERS = {
    "personas": _render_personas,
    "profiles": _render_profiles,
    "convergence": _render_convergence,
    "loop-invariants": _render_loop_invariants,
}


def render_block(block_id: str) -> str:
    return RENDERERS[block_id]()


def _apply(text: str) -> str:
    for block_id in RENDERERS:
        pattern = re.compile(
            r"(<!-- BEGIN GENERATED:%s -->\n).*?(\n<!-- END GENERATED:%s -->)"
            % (block_id, block_id),
            re.S,
        )
        text = pattern.sub(lambda m: m.group(1) + render_block(block_id) + m.group(2), text)
    return text


def sync(check: bool = False) -> list[str]:
    """Fill every marked region from code. Returns the list of out-of-sync doc paths
    (written when ``check`` is False, only reported when True)."""
    stale: list[str] = []
    for doc in DOCS:
        current = doc.read_text()
        updated = _apply(current)
        if updated != current:
            stale.append(str(doc))
            if not check:
                doc.write_text(updated)
    return stale


if __name__ == "__main__":
    changed = sync(check=False)
    print("\n".join(f"updated {c}" for c in changed) or "all skill docs already in sync")
