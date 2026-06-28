"""Run the adversarial loop on the dog-food domain and export a deterministic tree.

    export ANTHROPIC_API_KEY=...
    python examples/dog_food/run.py

Educational example only — not veterinary advice.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "input"))

import temper_skills
from schema import DogFoodQuery


def main() -> None:
    tree = temper_skills.ingest_skill(
        os.path.join(HERE, "input", "skill.md"),
        schema=DogFoodQuery,
        profile="standard",
        fn_name="can_dog_eat",
    )
    # Write to a gitignored path so this demo doesn't clobber the committed
    # canonical artifact (output/dog_food_checker.py, from a /temper subagent run).
    out = os.path.join(HERE, "output", "dog_food_checker.generated.py")
    tree.export(out)
    print(f"\nExported {out}\n")
    print(tree.to_source())


if __name__ == "__main__":
    main()
