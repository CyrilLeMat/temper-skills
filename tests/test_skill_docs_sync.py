"""Guard: the skill docs' generated tables must match the code they're sourced from.

This is what makes single-sourcing real — change PROFILES / a persona in code and forget
to regenerate, and this test fails with the fix command.
"""

from __future__ import annotations

from temper_skills.distill import PROFILES
from temper_skills.skill_docs import render_block, sync


def test_docs_in_sync_with_code():
    stale = sync(check=True)
    assert not stale, (
        "skill docs drifted from code — run `python -m temper_skills.skill_docs`:\n"
        + "\n".join(stale)
    )


def test_profiles_block_lists_every_profile_with_its_caps():
    block = render_block("profiles")
    for name, (max_rounds, stop_quiet, _i, _p) in PROFILES.items():
        assert f"`{name}`" in block
        assert f"| {max_rounds} | {stop_quiet} |" in block


def test_personas_block_marks_the_critic_always_on():
    block = render_block("personas")
    assert "overengineering_critic" in block
    assert "every round" in block


def test_convergence_block_is_plateau_not_threshold():
    block = render_block("convergence")
    assert "plateau" in block
    assert "threshold" in block  # explicitly contrasts against the old (drifted) rule
