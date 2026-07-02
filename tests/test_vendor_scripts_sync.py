"""CI guard: the vendored scripts/ copies must stay in sync with temper_skills/.

Same pattern as test_skill_docs_sync — the single source of truth is the package; the subagent
skill's scripts/ folder is a generated mirror. If someone edits temper_skills/{tree,export_tree,
update_validation}.py without re-running `python -m temper_skills.vendor_scripts`, this fails.
"""

from __future__ import annotations

from pathlib import Path

from temper_skills.vendor_scripts import MODULES, _DEST, render, vendor


def test_vendored_scripts_in_sync():
    stale = vendor(check=True)
    assert not stale, (
        f"vendored scripts drifted from temper_skills/: {stale}\n"
        "run: python -m temper_skills.vendor_scripts"
    )


def test_vendored_scripts_exist_and_are_flat_imports():
    for name in MODULES:
        p = _DEST / f"{name}.py"
        assert p.exists(), f"missing vendored script {p}"
        text = p.read_text()
        assert "VENDORED from temper_skills" in text
        # package-relative imports must have been flattened for standalone execution
        assert "from .tree import" not in text
        assert "from .export_tree import" not in text


def test_render_is_deterministic():
    for name in MODULES:
        assert render(name) == render(name)


def test_vendor_writes_missing_scripts(tmp_path, monkeypatch):
    from temper_skills import vendor_scripts

    dest = tmp_path / "scripts"
    monkeypatch.setattr(vendor_scripts, "_DEST", dest)
    stale = vendor_scripts.vendor(check=True)          # nothing exists yet
    assert len(stale) == len(MODULES) and not dest.exists()
    written = vendor_scripts.vendor(check=False)
    assert len(written) == len(MODULES)
    assert sorted(p.name for p in dest.iterdir()) == sorted(f"{m}.py" for m in MODULES)
    assert vendor_scripts.vendor(check=True) == []     # now in sync


def test_module_entrypoint_reports_in_sync(capsys):
    # the repo's vendored copies are in sync (guarded above), so this is a no-op run
    import runpy

    runpy.run_module("temper_skills.vendor_scripts", run_name="__main__")
    assert "in sync" in capsys.readouterr().out
