"""The author-facing audit report: findings derive from FitnessReport FIELDS (the pinned
scoring layer stays untouched), plus library discovery/ranking for `audit <dir>`."""

from __future__ import annotations

from pathlib import Path

from temper_skills.audit import FitnessReport
from temper_skills.audit_report import (
    LibraryRow,
    discover_skills,
    findings_of,
    headline_of,
    rank_key,
    render_audit_md,
    render_library_md,
    top_finding,
)


def _report(**over) -> FitnessReport:
    base = dict(
        fn_name="route_ticket", verdict="temper", decisiveness=9, combinatorics=8,
        stakes=8, distinct_decisions=1, schema_closure=1.0, open_features=[],
        n_features=4, rationale={}, recommended_action="temper",
        action_hint="run `temper-skills ingest`", reasons=[], caveats=[],
    )
    base.update(over)
    return FitnessReport(**base)


# ---- findings_of ----

def test_clean_temper_yields_single_good_finding():
    fs = findings_of(_report())
    assert [f.severity for f in fs] == ["good"]
    assert "test suite" in fs[0].fix


def test_flow_finding_points_at_decompose():
    fs = findings_of(_report(distinct_decisions=3, recommended_action="decompose"))
    assert any("3 separable decisions" in f.text and "decompose" in f.fix for f in fs)


def test_generation_finding_points_at_prose():
    fs = findings_of(_report(verdict="skip", decisiveness=2,
                             recommended_action="delegate_prose"))
    assert any("open-ended generation" in f.text and "prose" in f.fix for f in fs)


def test_open_features_fix_tracks_the_action():
    ext = findings_of(_report(verdict="caveats", combinatorics=5,
                              open_features=["food_item"],
                              recommended_action="externalize_data"))
    assert any("`food_item`" in f.text and "data file" in f.fix for f in ext)
    norm = findings_of(_report(verdict="caveats", open_features=["address"],
                               recommended_action="build_normalizer"))
    assert any("`address`" in f.text and "upstream" in f.fix for f in norm)


def test_lookup_shape_single_feature_and_low_stakes_findings():
    fs = findings_of(_report(verdict="caveats", combinatorics=4, stakes=3, n_features=1))
    texts = " | ".join(f.text for f in fs)
    assert "item-by-item lookup" in texts
    assert "one input feature" in texts
    assert "low-stakes" in texts.lower()


def test_no_jargon_in_findings():
    # The rendering layer must not leak the rubric's internal vocabulary.
    for rep in (_report(), _report(verdict="skip", decisiveness=2),
                _report(verdict="caveats", open_features=["x"], schema_closure=0.5)):
        for f in findings_of(rep):
            for word in ("H4", "closure", "caveat"):
                assert word not in f.text and word not in f.fix


# ---- headline_of ----

def test_headlines_are_author_facing():
    assert headline_of(_report())[0] == "FREEZE-WORTHY"
    assert headline_of(_report(verdict="caveats"))[0] == "FREEZE-WORTHY, WITH FINDINGS"
    assert headline_of(_report(verdict="skip"))[0] == "NOTHING TO FREEZE"
    label, gloss = headline_of(_report(distinct_decisions=3, recommended_action="decompose"))
    assert label == "SPLIT FIRST" and "~3 decisions" in gloss


# ---- render_audit_md ----

def test_audit_md_carries_headline_findings_and_scores():
    rep = _report(verdict="caveats", open_features=["food_item"],
                  recommended_action="externalize_data",
                  rationale={"combinatorics": "mostly a flat toxin lookup"})
    md = render_audit_md(rep, "skills/dog_food/skill.md")
    assert "# Skill audit — `skill.md`" in md
    assert "FREEZE-WORTHY, WITH FINDINGS" in md
    assert "`food_item`" in md
    assert "mostly a flat toxin lookup" in md
    assert "decisiveness 9/10" in md
    assert "`externalize_data`" in md


# ---- discovery ----

def test_discover_prefers_skill_md_convention(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "SKILL.md").write_text("# a")
    (tmp_path / "notes.md").write_text("# stray")
    assert [p.name for p in discover_skills(tmp_path)] == ["SKILL.md"]


def test_discover_fallback_skips_furniture_and_tempered(tmp_path):
    (tmp_path / "README.md").write_text("# readme")
    (tmp_path / "route.tempered.md").write_text("# output")
    (tmp_path / "route.md").write_text("# skill")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "x.md").write_text("# vcs")
    assert [p.name for p in discover_skills(tmp_path)] == ["route.md"]


def test_discover_empty(tmp_path):
    assert discover_skills(tmp_path) == []


# ---- ranking + library markdown ----

def test_rank_actionable_first_then_impact_errors_last(tmp_path):
    hot = LibraryRow(Path("hot.md"), report=_report(decisiveness=9, stakes=9))
    mild = LibraryRow(Path("mild.md"), report=_report(decisiveness=5, stakes=5))
    skip = LibraryRow(Path("skip.md"), report=_report(verdict="skip", decisiveness=2))
    err = LibraryRow(Path("bad.md"), error="boom")
    ordered = sorted([err, skip, mild, hot], key=rank_key)
    assert [r.path.name for r in ordered] == ["hot.md", "mild.md", "skip.md", "bad.md"]


def test_library_md_is_a_ranked_table_with_errors_inline():
    rows = [LibraryRow(Path("lib/a/SKILL.md"), report=_report()),
            LibraryRow(Path("lib/b.md"), error="no backend")]
    md = render_library_md(rows, "lib")
    assert "| skill | verdict |" in md
    assert "`a/SKILL.md`" in md and "FREEZE-WORTHY" in md
    assert "audit failed" in md and "no backend" in md
    assert top_finding(_report()) in md
