# VENDORED from temper_skills/export_tree.py — DO NOT EDIT.
# Regenerate: python -m temper_skills.vendor_scripts  (CI checks these stay in sync).
# Run standalone: python scripts/export_tree.py ...  (stdlib only, no install needed).
"""Deterministic tree → .py exporter, callable from the Claude Code skill.

The subagent-driven loop (see .claude/skills/temper-skills/SKILL.md) produces a
tree as JSON; this turns it into the zero-dependency Python module. No LLM here —
this is the deterministic half of the pipeline.

    python -m temper_skills.export_tree tree.json route.py
    cat tree.json | python -m temper_skills.export_tree - route.py

Alongside the module it writes, from ``tree.proposed_examples``:
  * ``<stem>.validation.jsonl`` — the committed validation dataset (the debate surface).
    Every case, with the tree's own prediction and an ``agrees`` flag. Disagreements are
    DATA, not test failures.
  * ``test_<stem>.py`` — behavior-lock tests that assert the tree's CURRENT output. Green
    by construction; they only go red on a real code regression (drift lock).
  * ``test_<stem>_ratified.py`` — assertions of the human-ratified labels ONLY. Emitted
    only when at least one case is ``status: "ratified"``. This one CAN go red — and
    should, if the tree ever contradicts blessed truth. That is the only sanctioned
    test failure; contested/proposed labels never become a failing (or xfail) test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tree import DecisionNode, DecisionTree


def _compile(tree: DecisionTree):
    # Inline (not validate.fn_from_tree) to keep this module import-light — the
    # deterministic export path must not pull in the LLM backends.
    ns: dict = {}
    exec(compile(tree.to_source(), f"<{tree.fn_name}>", "exec"), ns)
    return ns[tree.fn_name]


def _is_error(pred) -> bool:
    return isinstance(pred, str) and pred.startswith("ERROR")


def enrich_validation(tree: DecisionTree, raw: list[dict]) -> list[dict]:
    """Stamp each panel-drafted case with the tree's own prediction, agreement, and status.

    The subagent loop authors ``input``/``expected``/``rationale``/``source``; the *prediction*,
    the ``agrees`` flag, and the un-ratified default status are computed here deterministically,
    so a machine-authored label can never masquerade as ground truth. The result is the
    validation dataset — data, not assertions. A disagreement (``agrees is False``) is a number
    to review, never a failing test."""
    fn = _compile(tree)
    out: list[dict] = []
    for case in raw:
        try:
            prediction = fn(case["input"])
        except Exception as e:
            prediction = f"ERROR: {type(e).__name__}: {e}"
        expected = case.get("expected", "")
        agrees = None if (expected == "" or _is_error(prediction)) else (expected == prediction)
        record = {
            "input": case["input"],
            "expected": expected,
            "rationale": case.get("rationale", ""),
            "tree_prediction": prediction,
            # None = no proposed label to compare (or tree errored); else does the tree's
            # current answer match the proposed/ratified label?
            "agrees": agrees,
            # "proposed" = panel-authored, ungated; "resolved" = proposer settled a contested
            # cell (no domain oracle); "ratified" = a human domain owner blessed the label.
            "status": case.get("status", "proposed"),
        }
        # Pass through loop provenance if the case carries it (round/run id land here in the
        # per-round writer; harmless when absent).
        for k in ("source", "round", "first_seen_round", "run_id"):
            if case.get(k) is not None:
                record[k] = case[k]
        out.append(record)
    return out


# Back-compat alias — older callers/imports referenced enrich_proposed.
enrich_proposed = enrich_validation


def _canon(inp: dict) -> str:
    """Stable dedup key for a case input (feature order-independent)."""
    return json.dumps(inp, sort_keys=True, ensure_ascii=False)


def load_validation(path: str | Path) -> list[dict]:
    """Read an existing ``<stem>.validation.jsonl`` (the accumulating dataset), or [] if absent."""
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def merge_cases(existing: list[dict], new: list[dict], *,
                first_seen_round: int | None = None, run_id: str | None = None) -> list[dict]:
    """Merge freshly-proposed cases into the accumulated set, deduped by input.

    The first round to find a case owns its label/status and provenance; a later duplicate only
    appends its ``source`` (so we can see every persona/round that re-found it). Prediction and
    agreement are NOT set here — ``enrich_validation`` recomputes them against the current tree,
    so a tree change refreshes every row. Existing rows keep their order; new rows append."""
    by_key: dict[str, dict] = {}
    order: list[str] = []
    for row in existing:
        k = _canon(row["input"])
        if k not in by_key:
            by_key[k] = dict(row)
            order.append(k)
    for case in new:
        k = _canon(case["input"])
        if k in by_key:
            src = case.get("source")
            if src:
                row = by_key[k]
                srcs = [s for s in (row.get("source", "").split(";")) if s]
                if src not in srcs:
                    srcs.append(src)
                    row["source"] = ";".join(srcs)
            continue
        row = {
            "input": case["input"],
            "expected": case.get("expected", ""),
            "rationale": case.get("rationale", ""),
            "status": case.get("status", "proposed"),
        }
        if case.get("source"):
            row["source"] = case["source"]
        if first_seen_round is not None:
            row["first_seen_round"] = first_seen_round
        if run_id is not None:
            row["run_id"] = run_id
        by_key[k] = row
        order.append(k)
    return [by_key[k] for k in order]


def _dataset_score(enriched: list[dict]) -> dict:
    comparable = [c for c in enriched if c["agrees"] is not None]
    agree = sum(1 for c in comparable if c["agrees"])
    return {
        "total": len(enriched),
        "comparable": len(comparable),
        "agree": agree,
        "disputes": len(comparable) - agree,
        "ratified": sum(1 for c in enriched if c.get("status") == "ratified"),
    }


def write_dataset_and_tests(tree: DecisionTree, out_py: str, enriched: list[dict]) -> dict:
    """Write ``<stem>.validation.jsonl`` + the behavior-lock test + (only if any case is
    ratified) the ratified-truth test. Shared by ``export_tree`` (final) and
    ``update_validation`` (per round) so both produce byte-identical artifacts. Returns a
    score summary. A stale ``test_<stem>_ratified.py`` is removed when nothing is ratified."""
    out_path = Path(out_py)
    stem = str(out_path.with_suffix(""))
    Path(stem + ".validation.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in enriched))

    Path(out_path.with_name("test_" + out_path.name)).write_text(
        render_behavior_lock(out_path.stem, tree.fn_name, enriched))

    rat_path = out_path.with_name("test_" + out_path.stem + "_ratified.py")
    rat_src = render_ratified(out_path.stem, tree.fn_name, enriched)
    if rat_src is not None:
        rat_path.write_text(rat_src)
    elif rat_path.exists():
        rat_path.unlink()  # nothing ratified any more — don't leave a stale test

    return _dataset_score(enriched)


def _note(c: dict) -> str:
    return (c.get("source", "") + (" — " + c["rationale"] if c.get("rationale") else "")).strip(" —")


def render_behavior_lock(module: str, fn_name: str, enriched: list[dict]) -> str:
    """Committed pytest that locks the tree's CURRENT output for every case.

    Green by construction: it asserts what the tree returns, so it can only go red on a real
    code regression (a drift lock). Debates never live here — a contested case is still locked
    to the tree's own answer; the disagreement with the proposed label is recorded in the
    validation dataset, not as a test."""
    rows = [c for c in enriched if not _is_error(c["tree_prediction"])]
    L = [
        "# Auto-generated by temper-skills — DO NOT EDIT. Regenerate with export_tree.",
        f"# Behavior lock for {fn_name}: each case asserts the tree's CURRENT output.",
        "# Always green by construction — a failure here means the tree drifted (a real regression).",
        "# Debates are NOT here; they live in the .validation.jsonl dataset.",
        "import pytest",
        f"from {module} import {fn_name}",
        "",
        "# (input, tree_output, status, note)",
        "LOCKED = [",
    ]
    for c in rows:
        L.append(f"    ({c['input']!r}, {c['tree_prediction']!r}, {c['status']!r}, {_note(c)!r}),")
    L += [
        "]",
        "",
        '@pytest.mark.parametrize("case,expected,status,note", LOCKED, '
        'ids=[c[3][:60] for c in LOCKED])',
        f"def test_{fn_name}_behavior(case, expected, status, note):",
        f"    assert {fn_name}(case) == expected",
        "",
    ]
    return "\n".join(L)


def render_ratified(module: str, fn_name: str, enriched: list[dict]) -> str | None:
    """Committed pytest asserting the tree honors every RATIFIED validation label.

    Unlike the behavior lock, this CAN go red — and should, if the tree ever contradicts a
    human-blessed answer. That is the only sanctioned test failure in the pipeline. Returns
    None when nothing is ratified yet (no file is written), so a run never carries an empty or
    xfail placeholder — open disputes stay as data in the dataset until a human rules."""
    rows = [c for c in enriched
            if c.get("status") == "ratified" and c.get("expected") not in ("", None)
            and not _is_error(c["tree_prediction"])]
    if not rows:
        return None
    L = [
        "# Auto-generated by temper-skills — DO NOT EDIT. Regenerate with export_tree.",
        f"# Ratified-truth tests for {fn_name}: assert the tree matches HUMAN-blessed labels.",
        "# This file CAN fail — a red test here means the tree contradicts ratified ground truth.",
        "import pytest",
        f"from {module} import {fn_name}",
        "",
        "# (input, ratified_label, note)",
        "RATIFIED = [",
    ]
    for c in rows:
        L.append(f"    ({c['input']!r}, {c['expected']!r}, {_note(c)!r}),")
    L += [
        "]",
        "",
        '@pytest.mark.parametrize("case,expected,note", RATIFIED, ids=[c[2][:60] for c in RATIFIED])',
        f"def test_{fn_name}_ratified(case, expected, note):",
        f"    assert {fn_name}(case) == expected",
        "",
    ]
    return "\n".join(L)


def tree_from_dict(data: dict) -> DecisionTree:
    nodes = [
        DecisionNode(
            condition=n["condition"],
            outcome=n["outcome"],
            rounds_survived=int(n.get("rounds_survived", 1)),
            sources=list(n.get("sources", [])),
            critic_note=n.get("critic_note"),
            gray_zone=n.get("gray_zone"),
        )
        for n in data["nodes"]
    ]
    return DecisionTree(
        nodes=nodes,
        default_outcome=data["default_outcome"],
        features=list(data.get("features", [])),
        fn_name=data.get("fn_name", "decide"),
        model=data.get("model", "claude-code-subagents"),
        profile=data.get("profile", "standard"),
        constraints_version=data.get("constraints_version", "v1.0"),
        include_provenance=bool(data.get("include_provenance", True)),
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        print("usage: python -m temper_skills.export_tree <tree.json|-> <out.py>", file=sys.stderr)
        return 2
    src, out = argv
    raw = sys.stdin.read() if src == "-" else open(src).read()
    data = json.loads(raw)
    tree = tree_from_dict(data)
    tree.export(out)
    print(f"exported {out} ({len(tree.nodes)} nodes)")

    # Case source: fold tree.json's proposed_examples into any dataset the per-round loop already
    # accumulated on disk, so a final export refreshes predictions without clobbering provenance.
    stem = str(Path(out).with_suffix(""))
    existing = load_validation(stem + ".validation.jsonl")
    from_tree = data.get("proposed_examples") or []
    if existing or from_tree:
        merged = merge_cases(existing, from_tree)
        enriched = enrich_validation(tree, merged)
        s = write_dataset_and_tests(tree, out, enriched)
        score = f"{s['agree']}/{s['comparable']}" if s["comparable"] else "n/a"
        print(f"wrote {s['total']} validation case(s) → {stem}.validation.jsonl")
        print(f"  tree agrees with {score} labelled case(s); "
              f"{s['disputes']} open disagreement(s) (data, not failures — review to ratify)")
        print(f"wrote behavior-lock tests (always green) → "
              f"{Path(out).with_name('test_' + Path(out).name)}")
        if s["ratified"]:
            print(f"wrote ratified-truth tests ({s['ratified']} case(s), can fail on regression)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
