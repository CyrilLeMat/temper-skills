"""Guard: the subagent SKILL.md's loop NARRATIVE must state the same algorithm as
distill.py.

The narrative is instructions for an orchestrating agent — genuine prose, so it can't
be generated the way the tables and the loop-invariants fact card are (those are
guarded by test_skill_docs_sync). Instead, every algorithmic CLAIM the prose makes is
pinned here. A failure means code and prose diverged: fix whichever is wrong, knowingly.
This exists because the drift is real — the harvest-exclusion sentence shipped naming
one excluded persona while the code excluded three.
"""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

from temper_skills.distill import _EARN_ROUNDS, HARVEST_EXCLUDED
from temper_skills.validation_case import ValidationCase

_SKILL = (Path(__file__).resolve().parents[1]
          / ".claude/skills/temper-skills/SKILL.md").read_text()


def test_earn_a_branch_window_matches_the_code():
    mentions = re.findall(r"~(\d+) rounds", _SKILL)
    assert mentions, "the earn-a-branch narrative disappeared — update this guard too"
    assert all(int(n) == _EARN_ROUNDS for n in mentions), (
        f"prose says an added feature must earn a branch in {set(mentions)} rounds; "
        f"distill._EARN_ROUNDS is {_EARN_ROUNDS}"
    )


def test_harvest_exclusions_name_every_excluded_persona():
    sentence = re.search(r"harvest the `proposed_tests`.{0,500}?writer", _SKILL, re.S)
    assert sentence, "the harvest instruction disappeared — update this guard too"
    for name in HARVEST_EXCLUDED:
        assert name in sentence.group(0), (
            f"the harvest instruction must exclude `{name}` (distill.HARVEST_EXCLUDED) — "
            "a subagent following the prose would collect cases the library rejects"
        )


def test_gate_choices_match_the_cli_gate():
    # The one blocking interaction: Continue / Stop (and review) / Abort — same triple
    # the CLI gate offers (cli._make_gate).
    assert re.search(r"Continue.{0,40}Stop.{0,40}Abort", _SKILL)


def test_proposed_test_shape_is_a_subset_of_the_case_contract():
    m = re.search(r"`proposed_test` is a `\{([^}]*)\}", _SKILL)
    assert m, "the proposed_test shape line disappeared — update this guard too"
    prose_fields = {part.split(":")[0].strip() for part in m.group(1).split(",")}
    contract = {f.name for f in fields(ValidationCase)}
    assert prose_fields <= contract, (
        f"prose names case fields {prose_fields - contract} that ValidationCase "
        "does not define"
    )
