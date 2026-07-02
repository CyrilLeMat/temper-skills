"""Per-round incremental validation writer."""

from __future__ import annotations

import json

from temper_skills.update_validation import main, update

# A tree whose logic we can flip between rounds to prove predictions refresh.
TREE_V1 = {
    "fn_name": "route",
    "features": ["x"],
    "default_outcome": "low",
    "nodes": [{"condition": "x is not None and x >= 10", "outcome": "high"}],
}
# v2 lowers the threshold: x==5 now routes "high" where v1 said "low".
TREE_V2 = {
    "fn_name": "route",
    "features": ["x"],
    "default_outcome": "low",
    "nodes": [{"condition": "x is not None and x >= 5", "outcome": "high"}],
}


def _rows(out_py):
    stem = out_py.with_suffix("")
    return [json.loads(ln) for ln in (stem.parent / (stem.name + ".validation.jsonl"))
            .read_text().splitlines() if ln.strip()]


def test_new_cases_get_round_and_run_id_stamped(tmp_path):
    out = tmp_path / "route.py"
    update(TREE_V1, str(out), [{"input": {"x": 5}, "expected": "low", "source": "ech#r1"}],
           round=1, run_id="RUN-A")
    rows = _rows(out)
    assert len(rows) == 1
    assert rows[0]["first_seen_round"] == 1 and rows[0]["run_id"] == "RUN-A"
    assert rows[0]["tree_prediction"] == "low" and rows[0]["agrees"] is True


def test_dedup_across_rounds_keeps_first_provenance_and_appends_source(tmp_path):
    out = tmp_path / "route.py"
    update(TREE_V1, str(out), [{"input": {"x": 5}, "expected": "low", "source": "ech#r1"}],
           round=1, run_id="RUN-A")
    # round 2 re-finds the same input (different persona) and adds a genuinely new one
    update(TREE_V1, str(out), [
        {"input": {"x": 5}, "expected": "low", "source": "domain_expert#r2"},
        {"input": {"x": 20}, "expected": "high", "source": "ech#r2"},
    ], round=2, run_id="RUN-A")
    rows = _rows(out)
    assert len(rows) == 2                                  # deduped, not 3
    dup = next(r for r in rows if r["input"] == {"x": 5})
    assert dup["first_seen_round"] == 1                    # first round owns provenance
    assert "ech#r1" in dup["source"] and "domain_expert#r2" in dup["source"]
    fresh = next(r for r in rows if r["input"] == {"x": 20})
    assert fresh["first_seen_round"] == 2


def test_tree_change_refreshes_predictions_and_agreement(tmp_path):
    out = tmp_path / "route.py"
    update(TREE_V1, str(out), [{"input": {"x": 5}, "expected": "high", "source": "ech#r1"}],
           round=1, run_id="RUN-A")
    r1 = _rows(out)[0]
    assert r1["tree_prediction"] == "low" and r1["agrees"] is False   # v1: x=5 -> low, disputes "high"
    # a quiet round (no new cases) under the changed tree must still refresh the row
    update(TREE_V2, str(out), [], round=2, run_id="RUN-A")
    r2 = _rows(out)[0]
    assert r2["tree_prediction"] == "high" and r2["agrees"] is True   # v2: x=5 -> high, now agrees


def test_behavior_lock_always_green_and_ratified_only_when_present(tmp_path):
    out = tmp_path / "route.py"
    # a disputed proposed case must NOT create a failing/xfail test
    update(TREE_V1, str(out), [{"input": {"x": 5}, "expected": "high"}], round=1, run_id="R")
    lock = (tmp_path / "test_route.py").read_text()
    assert "xfail" not in lock and "def test_route_behavior" in lock
    assert "'low'" in lock                                 # locked to the tree's answer, not "high"
    assert not (tmp_path / "test_route_ratified.py").exists()

    # ratifying a case (agreeing with the tree) writes the ratified test
    update(TREE_V1, str(out),
           [{"input": {"x": 20}, "expected": "high", "status": "ratified"}], round=2, run_id="R")
    assert (tmp_path / "test_route_ratified.py").exists()
    assert "def test_route_ratified" in (tmp_path / "test_route_ratified.py").read_text()


def test_new_count_reported(tmp_path):
    out = tmp_path / "route.py"
    s1 = update(TREE_V1, str(out), [{"input": {"x": 5}}, {"input": {"x": 6}}], round=1, run_id="R")
    assert s1["new"] == 2 and s1["total"] == 2
    s2 = update(TREE_V1, str(out), [{"input": {"x": 5}}, {"input": {"x": 7}}], round=2, run_id="R")
    assert s2["new"] == 1 and s2["total"] == 3            # x=5 already known


def test_cli_reads_stdin(tmp_path, monkeypatch):
    import io
    tree_path = tmp_path / "tree.json"
    tree_path.write_text(json.dumps(TREE_V1))
    out = tmp_path / "route.py"
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([{"input": {"x": 5}, "expected": "low"}])))
    rc = main([str(tree_path), str(out), "--round", "1", "--run-id", "RUN-CLI"])
    assert rc == 0
    rows = _rows(out)
    assert rows[0]["run_id"] == "RUN-CLI" and rows[0]["first_seen_round"] == 1


def test_cli_empty_stdin_is_a_quiet_refresh(tmp_path, monkeypatch):
    import io
    tree_path = tmp_path / "tree.json"; tree_path.write_text(json.dumps(TREE_V1))
    out = tmp_path / "route.py"
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main([str(tree_path), str(out), "--round", "1"]) == 0
    # no cases, no dataset file needed, but it must not crash
    assert not (tmp_path / "route.validation.jsonl").exists() or _rows(out) == []


def test_main_usage_error_on_wrong_positionals(capsys):
    assert main([]) == 2
    assert "usage:" in capsys.readouterr().err


def test_main_rejects_non_list_stdin(tmp_path, monkeypatch, capsys):
    import io

    tree = tmp_path / "tree.json"
    tree.write_text(json.dumps(TREE_V1))
    monkeypatch.setattr("sys.stdin", io.StringIO('{"input": {"x": 1}}'))
    assert main([str(tree), str(tmp_path / "route.py")]) == 2
    assert "JSON list" in capsys.readouterr().err


def test_main_happy_path_with_flag_forms(tmp_path, monkeypatch, capsys):
    import io

    tree = tmp_path / "tree.json"
    tree.write_text(json.dumps(TREE_V1))
    out = tmp_path / "route.py"
    cases = [{"input": {"x": 20}, "expected": "high", "source": "ech#r3"}]
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(cases)))
    assert main(["--round=3", "--run-id=RUN-B", str(tree), str(out)]) == 0
    assert "[round 3]" in capsys.readouterr().out
    rows = _rows(out)
    assert rows[0]["first_seen_round"] == 3 and rows[0]["run_id"] == "RUN-B"


def test_module_entrypoint(tmp_path, monkeypatch):
    import io
    import runpy
    import sys

    import pytest

    tree = tmp_path / "tree.json"
    tree.write_text(json.dumps(TREE_V1))
    monkeypatch.setattr(sys, "argv",
                        ["update_validation", str(tree), str(tmp_path / "route.py")])
    monkeypatch.setattr("sys.stdin", io.StringIO("[]"))
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("temper_skills.update_validation", run_name="__main__")
    assert exc.value.code == 0
