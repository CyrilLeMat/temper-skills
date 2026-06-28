"""Run the adversarial loop on the dog-food domain and export a deterministic tree.

    export ANTHROPIC_API_KEY=...
    python examples/dog_food/run.py

Educational example only — not veterinary advice.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import temper_skills
from schema import DogFoodQuery

HERE = os.path.dirname(__file__)


def main() -> None:
    tree = temper_skills.ingest_skill(
        os.path.join(HERE, "skill.md"),
        schema=DogFoodQuery,
        profile="standard",
        fn_name="can_dog_eat",
    )
    # Write to a gitignored path so this demo doesn't clobber the committed
    # canonical artifact (dog_food_checker.py, produced by a /temper subagent run).
    out = os.path.join(HERE, "dog_food_checker.generated.py")
    tree.export(out)
    print(f"\nExported {out}\n")
    print(tree.to_source())


if __name__ == "__main__":
    main()
