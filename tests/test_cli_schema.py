"""_load_schema: pin a schema from a .py:Class or a .json file."""

from __future__ import annotations

import json

from pydantic import BaseModel

from temper_skills.cli import _load_schema


def test_load_pydantic_from_pyfile(tmp_path):
    p = tmp_path / "schema.py"
    p.write_text(
        "from pydantic import BaseModel\n"
        "class Q(BaseModel):\n    food_item: str\n    dog_weight_kg: float\n"
    )
    cls = _load_schema(f"{p}:Q")
    assert issubclass(cls, BaseModel)
    assert set(cls.model_json_schema()["properties"]) == {"food_item", "dog_weight_kg"}


def test_load_json_schema(tmp_path):
    p = tmp_path / "schema.json"
    p.write_text(json.dumps({"type": "object", "properties": {"x": {"type": "string"}}}))
    assert _load_schema(str(p))["properties"] == {"x": {"type": "string"}}


def test_load_pyfile_without_class_errors(tmp_path):
    p = tmp_path / "schema.py"
    p.write_text("x = 1\n")
    try:
        _load_schema(str(p))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_loads_the_example_dogfoodquery():
    cls = _load_schema("examples/dog_food/ratified/schema.py:DogFoodQuery")
    props = set(cls.model_json_schema()["properties"])
    assert {"food_item", "food_form", "dog_weight_kg", "quantity_grams"} <= props
