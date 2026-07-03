"""Per-round incremental writer for the validation dataset.

The subagent loop (see .claude/skills/temper-skills/SKILL.md) calls this ONCE PER ROUND so the
committed ``<stem>.validation.jsonl`` — and the behavior-lock tests beside it — grow on disk as
the panel finds cases, instead of only at export. Deterministic, no LLM.

Each round it:
  * merges the round's newly proposed cases into the accumulated dataset (dedup by input; the
    round that first found a case owns its label/status, later duplicates only add their source);
  * stamps each new case with the round + run id that discovered it (the audit trail — is this
    case from *this* session?);
  * refreshes EVERY row's ``tree_prediction`` / ``agrees`` against the CURRENT tree, since the
    tree changed this round;
  * rewrites the behavior-lock test (always green) and the ratified-truth test (only if any case
    is ratified).

Disagreements are recorded as data (``"agrees": false``), never as failing or xfail tests.

    # new cases (a JSON list of {input, expected?, rationale?, source?}) on stdin
    python -m temper_skills.update_validation <tree.json> <out.py> --round 3 --run-id <id> < cases.json
    # a quiet round that found nothing still refreshes predictions against the new tree:
    echo '[]' | python -m temper_skills.update_validation <tree.json> <out.py> --round 4 --run-id <id>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .export_tree import (
    enrich_validation,
    load_validation,
    merge_cases,
    tree_from_dict,
    write_dataset_and_tests,
)


def update(
    tree_json: dict,
    out_py: str,
    new_cases: list[dict],
    *,
    round: int | None = None,
    run_id: str | None = None,
) -> dict:
    """Merge ``new_cases`` into the dataset beside ``out_py`` and refresh against the tree.

    Returns the score summary from :func:`export_tree.write_dataset_and_tests`, plus ``new`` —
    how many inputs this round added that weren't already accumulated."""
    tree = tree_from_dict(tree_json)
    stem = str(Path(out_py).with_suffix(""))
    existing = load_validation(stem + ".validation.jsonl")
    before = {json.dumps(r["input"], sort_keys=True, ensure_ascii=False) for r in existing}

    merged = merge_cases(existing, new_cases, first_seen_round=round, run_id=run_id)
    enriched = enrich_validation(tree, merged)
    summary = write_dataset_and_tests(tree, out_py, enriched)
    after = {json.dumps(r["input"], sort_keys=True, ensure_ascii=False) for r in enriched}
    summary["new"] = len(after - before)
    return summary


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    round_no: int | None = None
    run_id: str | None = None
    positional: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--round":
            i += 1
            round_no = int(argv[i])
        elif a.startswith("--round="):
            round_no = int(a.split("=", 1)[1])
        elif a == "--run-id":
            i += 1
            run_id = argv[i]
        elif a.startswith("--run-id="):
            run_id = a.split("=", 1)[1]
        else:
            positional.append(a)
        i += 1

    if len(positional) != 2:
        print(
            "usage: python -m temper_skills.update_validation <tree.json> <out.py> "
            "[--round N] [--run-id ID]  (new cases as JSON list on stdin)",
            file=sys.stderr,
        )
        return 2

    tree_path, out_py = positional
    tree_json = json.loads(open(tree_path).read())
    raw = sys.stdin.read().strip()
    new_cases = json.loads(raw) if raw else []
    if not isinstance(new_cases, list):
        print("stdin must be a JSON list of cases (or empty)", file=sys.stderr)
        return 2

    s = update(tree_json, out_py, new_cases, round=round_no, run_id=run_id)
    stem = str(Path(out_py).with_suffix(""))
    tag = f"round {round_no}" if round_no is not None else "update"
    score = f"{s['agree']}/{s['comparable']}" if s["comparable"] else "n/a"
    print(
        f"[{tag}] {stem}.validation.jsonl: {s['total']} case(s) (+{s['new']} new); "
        f"tree agrees {score}; {s['disputes']} open disagreement(s)"
        + (f"; {s['ratified']} ratified" if s["ratified"] else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
