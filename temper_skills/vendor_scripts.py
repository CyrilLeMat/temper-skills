"""Vendor the pure-stdlib deterministic exporters into the subagent skill's ``scripts/`` dir.

The subagent-mode skill (``.claude/skills/temper-skills/``) shells out to these to export the
tree, write the per-round validation dataset, and emit behavior-lock tests. Vendoring them —
they are stdlib-only — makes that skill **self-contained**, honoring both its "no install"
promise and the Agent Skills ``scripts/`` convention (it previously shelled out to the installed
``temper_skills`` package).

The single source of truth stays in ``temper_skills/``. This copies each module into
``scripts/`` and rewrites the package-relative imports to flat ones (``scripts/`` is one
directory, so ``python scripts/export_tree.py`` puts it first on ``sys.path``). ``vendor()``
writes them; ``vendor(check=True)`` reports any that drifted (the CI guard — see
``tests/test_vendor_scripts_sync.py``). Edit the source, then run
``python -m temper_skills.vendor_scripts``.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DEST = _ROOT / ".claude/skills/temper-skills/scripts"
# Pure-stdlib only. export_skill is intentionally excluded (it pulls in pydantic for the
# LLM-facing WovenSkill); skill_render carries the pydantic-free rendering + spec skill-dir
# arrangement, so subagent mode can emit a full Agent Skill dir with no install.
MODULES = ["tree", "validation_case", "export_tree", "update_validation", "skill_render"]

_BANNER = (
    "# VENDORED from temper_skills/{name}.py — DO NOT EDIT.\n"
    "# Regenerate: python -m temper_skills.vendor_scripts  (CI checks these stay in sync).\n"
    "# Run standalone: python scripts/{name}.py ...  (stdlib only, no install needed).\n"
)


def _transform(name: str, src: str) -> str:
    # scripts/ is a flat directory on sys.path[0], so package-relative imports become plain.
    src = src.replace("from .tree import", "from tree import")
    src = src.replace("from .export_tree import", "from export_tree import")
    src = src.replace("from .validation_case import", "from validation_case import")
    return _BANNER.format(name=name) + src


def render(name: str) -> str:
    """The vendored text for one module (source + banner + flattened imports)."""
    return _transform(name, (_ROOT / "temper_skills" / f"{name}.py").read_text())


def vendor(check: bool = False) -> list[str]:
    """Sync scripts/ from the package. Returns the paths that were (or need to be) rewritten."""
    stale: list[str] = []
    for name in MODULES:
        want = render(name)
        dest = _DEST / f"{name}.py"
        have = dest.read_text() if dest.exists() else None
        if have != want:
            stale.append(str(dest))
            if not check:
                _DEST.mkdir(parents=True, exist_ok=True)
                dest.write_text(want)
    return stale


if __name__ == "__main__":
    changed = vendor(check=False)
    print("\n".join(f"vendored {c}" for c in changed) or "vendored scripts already in sync")
