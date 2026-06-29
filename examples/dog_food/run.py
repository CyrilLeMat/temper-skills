"""Bootstrap the dog-food tree from *only* the skill — no schema, no validation set.

    export ANTHROPIC_API_KEY=...
    python examples/dog_food/run.py

This is the "input any skill, extract deterministic logic" path: the loop infers the
feature schema from the prose and drafts test cases for its own gray zones. Both are
*proposals* — the committed ``output/schema.py`` and ``output/validation_set.json`` are what
a human signed off on.

Educational example only — not veterinary advice.
"""

from __future__ import annotations

import json
import os

import temper_skills

HERE = os.path.dirname(__file__)


def main() -> None:
    # schema=None → the loop proposes the feature schema from the skill itself.
    tree = temper_skills.ingest_skill(
        os.path.join(HERE, "input", "skill.md"),
        schema=None,
        profile="standard",
        fn_name="can_dog_eat",
    )
    # Gitignored path so this demo doesn't clobber the committed canonical artifact
    # (output/dog_food_checker.py, from a /temper subagent run).
    out = os.path.join(HERE, "output", "dog_food_checker.generated.py")
    tree.export(out)
    print(f"\nExported {out}\n")
    print(tree.to_source())

    proposed = getattr(tree, "proposed_examples", None)
    if proposed:
        sidecar = os.path.join(HERE, "output", "dog_food.proposed_examples.json")
        with open(sidecar, "w") as f:
            json.dump(proposed, f, indent=2, ensure_ascii=False)
        print(f"\nThe loop drafted {len(proposed)} test case(s) → {sidecar}")
        print("Review/ratify them to grow a validation set (cf. output/validation_set.json).")


if __name__ == "__main__":
    main()
