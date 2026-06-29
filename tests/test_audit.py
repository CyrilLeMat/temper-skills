"""The temper-fitness pre-flight — the gate that keeps the loop off a bad fit.

The verdict is a pure function of four scored axes, so it's pinned here without network.
The combos below mirror the four shipped examples: the rubric thresholds are a judgement
call, and any change to them must show up as a diff in these expectations.
"""

from __future__ import annotations

from temper_skills.audit import (
    AUDIT_SYSTEM,
    FitnessReport,
    JudgeScores,
    audit_skill,
    schema_closure,
    verdict_of,
)
from temper_skills.backends.base import Backend
from temper_skills.ingest import InferredFeature, InferredSchema


def _schema(*features: InferredFeature, fn_name="decide") -> InferredSchema:
    return InferredSchema(fn_name=fn_name, features=list(features))


def _enum(name: str) -> InferredFeature:
    return InferredFeature(name=name, type="string", description="one of a, b, c")


def _free(name: str) -> InferredFeature:
    return InferredFeature(name=name, type="string", description="the item's name")


# ---- schema_closure: open free-text vs closed spaces ----

def test_closure_empty_schema_is_zero():
    assert schema_closure(_schema()) == 0.0


def test_closure_free_text_only_is_zero():
    assert schema_closure(_schema(_free("food_item"))) == 0.0


def test_closure_nonstring_counts_closed():
    s = _schema(
        InferredFeature(name="score", type="number"),
        InferredFeature(name="flag", type="boolean"),
    )
    assert schema_closure(s) == 1.0


def test_closure_enum_like_string_counts_closed():
    s = _schema(_enum("priority"), _free("note"))
    assert schema_closure(s) == 0.5


# ---- verdict_of: the rubric, keyed to the shipped examples ----

def test_generation_skill_skips():
    # decisiveness < 4 — nothing to freeze
    v, reasons, caveats = verdict_of(JudgeScores(decisiveness=2, combinatorics=5, stakes=5), 1.0, 3)
    assert v == "skip"
    assert "generation" in reasons[0]


def test_dog_food_flat_lookup_skips():
    # flat free-text lookup: closure 0, combinatorics low — the documented thrash mode
    v, reasons, _ = verdict_of(JudgeScores(decisiveness=6, combinatorics=2, stakes=5), 0.0, 1)
    assert v == "skip"
    assert "H4" in reasons[0]


def test_ticket_routing_tempers_clean():
    # enums + score + bool, real interactions — the sweet spot
    v, _, caveats = verdict_of(JudgeScores(decisiveness=9, combinatorics=8, stakes=8), 1.0, 4)
    assert v == "temper"
    assert caveats == []


def test_license_compat_tempers_clean():
    v, _, caveats = verdict_of(JudgeScores(decisiveness=9, combinatorics=9, stakes=7), 1.0, 3)
    assert v == "temper"
    assert caveats == []


def test_partial_closure_tempers_with_caveat():
    # decisive + interacting, but a leaky schema — temperable, flagged
    v, _, caveats = verdict_of(JudgeScores(decisiveness=8, combinatorics=7, stakes=6), 0.5, 2)
    assert v == "caveats"
    assert any("normalizer" in c for c in caveats)


def test_single_feature_flagged_when_otherwise_a_fit():
    v, _, caveats = verdict_of(JudgeScores(decisiveness=8, combinatorics=6, stakes=6), 1.0, 1)
    assert v == "caveats"
    assert any("single feature" in c for c in caveats)


def test_low_stakes_flagged():
    v, _, caveats = verdict_of(JudgeScores(decisiveness=8, combinatorics=6, stakes=2), 1.0, 3)
    assert v == "caveats"
    assert any("stakes" in c for c in caveats)


def test_marginal_combinatorics_survives_if_schema_closed():
    # closure >= 0.5 keeps it out of the hard skip even when combinatorics is weak
    v, _, _ = verdict_of(JudgeScores(decisiveness=7, combinatorics=3, stakes=6), 1.0, 3)
    assert v in {"temper", "caveats"}


# ---- audit_skill end-to-end on a scripted backend (no network) ----

class _AuditBackend(Backend):
    name = "fake"

    def __init__(self, scores: JudgeScores, schema: InferredSchema):
        super().__init__("fake-model")
        self._scores = scores
        self._schema = schema

    def complete(self, system, user, schema):
        if schema is InferredSchema:
            return self._schema
        if schema is JudgeScores:
            return self._scores
        raise AssertionError(f"unexpected schema {schema}")


def test_audit_skill_infers_schema_then_judges(tmp_path):
    skill = tmp_path / "skill.md"
    skill.write_text("# route tickets by priority and security")
    be = _AuditBackend(
        JudgeScores(decisiveness=9, combinatorics=8, stakes=8),
        _schema(_enum("priority"), InferredFeature(name="security_score", type="number"),
                fn_name="route_ticket"),
    )
    report = audit_skill(str(skill), backend=be)
    assert isinstance(report, FitnessReport)
    assert report.fn_name == "route_ticket"
    assert report.verdict == "temper"
    assert report.schema_closure == 1.0


def test_audit_skill_pinned_schema_skips_inference(tmp_path):
    skill = tmp_path / "skill.md"
    skill.write_text("# can my dog eat that?")
    pinned = _schema(_free("food_item"), fn_name="can_dog_eat")
    be = _AuditBackend(JudgeScores(decisiveness=6, combinatorics=2, stakes=5), pinned)
    report = audit_skill(str(skill), backend=be, schema=pinned)
    assert report.verdict == "skip"
    assert report.fn_name == "can_dog_eat"


def test_audit_system_prompt_names_the_axes():
    for axis in ("decisiveness", "combinatorics", "stakes"):
        assert axis in AUDIT_SYSTEM
