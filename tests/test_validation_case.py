"""The validation-case contract: one definition of the row shape, stable on-disk key
order, tolerant parsing — plus the named scoring keys' tie-break semantics."""

from __future__ import annotations

from temper_skills.distill import AdoptKey, SelectKey
from temper_skills.export_tree import enrich_validation, merge_cases
from temper_skills.tree import DecisionNode, DecisionTree
from temper_skills.validation_case import ValidationCase, canon


# ---- the record shape ----


def test_merged_row_key_order_is_stable():
    rec = ValidationCase(
        input={"a": 1},
        expected="yes",
        rationale="r",
        source="edge_case_hunter (round 2)",
        first_seen_round=2,
        run_id="rid",
    ).to_record()
    assert list(rec) == [
        "input",
        "expected",
        "rationale",
        "status",
        "source",
        "first_seen_round",
        "run_id",
    ]
    assert rec["status"] == "proposed"


def test_enriched_row_carries_prediction_and_tristate_agrees():
    rec = ValidationCase(input={"a": 1}, expected="", tree_prediction="no", agrees=None).to_record()
    assert list(rec) == ["input", "expected", "rationale", "tree_prediction", "agrees", "status"]
    assert rec["agrees"] is None  # meaningful: no label to compare — must be emitted


def test_optional_keys_absent_when_unset():
    rec = ValidationCase(input={"a": 1}, expected="yes").to_record()
    assert "source" not in rec and "run_id" not in rec and "tree_prediction" not in rec


def test_from_dict_tolerates_unknown_keys_and_round_trips():
    row = {
        "input": {"a": 1},
        "expected": "yes",
        "status": "ratified",
        "round": 3,
        "some_future_field": "ignored",
    }
    vc = ValidationCase.from_dict(row)
    assert vc.status == "ratified" and vc.round == 3
    assert vc.to_record()["status"] == "ratified"


def test_canon_is_order_independent():
    assert canon({"a": 1, "b": 2}) == canon({"b": 2, "a": 1})


# ---- the contract survives the real merge → enrich pipeline ----


def _tree():
    return DecisionTree(
        nodes=[DecisionNode(condition='x == "hot"', outcome="yes")],
        default_outcome="no",
        features=["x"],
        fn_name="decide",
    )


def test_merge_then_enrich_produces_contract_rows():
    merged = merge_cases(
        [],
        [
            {"input": {"x": "hot"}, "expected": "yes", "source": "hunter"},
            {"input": {"x": "cold"}, "expected": "yes"},  # will disagree with the tree
        ],
        first_seen_round=1,
        run_id="r1",
    )
    enriched = enrich_validation(_tree(), merged)
    assert [e["agrees"] for e in enriched] == [True, False]
    for e in enriched:
        vc = ValidationCase.from_dict(e)  # every row parses back
        assert vc.first_seen_round == 1 and vc.run_id == "r1"
        assert e == vc.to_record()  # and re-renders identically


# ---- scoring keys: the two tie-break semantics, pinned ----


def test_adopt_key_ties_break_toward_the_smaller_tree():
    assert AdoptKey(1.0, 0.8, parsimony=-3) > AdoptKey(1.0, 0.8, parsimony=-5)
    # correctness always dominates parsimony
    assert AdoptKey(1.0, 0.9, parsimony=-9) > AdoptKey(1.0, 0.8, parsimony=-1)


def test_select_key_ties_break_toward_the_panel_mean():
    assert SelectKey(1.0, 0.8, panel_mean=8.2) > SelectKey(1.0, 0.8, panel_mean=7.9)
    assert SelectKey(1.0, 0.9, panel_mean=1.0) > SelectKey(1.0, 0.8, panel_mean=10.0)
