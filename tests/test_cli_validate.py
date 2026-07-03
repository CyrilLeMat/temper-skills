"""The `temper-skills validate` command end-to-end — the CI gate the README sells."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from temper_skills.cli import app

runner = CliRunner()

TREE = {
    "fn_name": "route",
    "features": ["x"],
    "default_outcome": "low",
    "nodes": [{"condition": "x is not None and x >= 10", "outcome": "high — big"}],
}


@pytest.fixture
def artifacts(tmp_path):
    tree = tmp_path / "tree.json"
    tree.write_text(json.dumps(TREE))
    data = tmp_path / "set.json"
    data.write_text(
        json.dumps(
            [
                {"input": {"x": 12}, "expected": "high"},
                {"input": {"x": 1}, "expected": "low"},
            ]
        )
    )
    return tree, data


def test_validate_passes_on_agreement(artifacts):
    tree, data = artifacts
    r = runner.invoke(app, ["validate", str(tree), str(data)])
    assert r.exit_code == 0
    assert "2/2" in r.output


def test_validate_fails_below_threshold(artifacts, tmp_path):
    tree, _ = artifacts
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"input": {"x": 12}, "expected": "low"}]))
    r = runner.invoke(app, ["validate", str(tree), str(bad)])
    assert r.exit_code == 1
    assert "0/1" in r.output


def test_validate_rejects_unknown_comparator(artifacts):
    tree, data = artifacts
    r = runner.invoke(app, ["validate", str(tree), str(data), "--match", "fuzzy"])
    assert r.exit_code == 2
