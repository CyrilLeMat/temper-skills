"""Temper the sprained-ankle first-aid skill into a deterministic advisor.

    export ANTHROPIC_API_KEY=...   # or any provider / vertex / agent CLI
    python examples/ankle_sprain/run.py

⚠️ Educational example only — NOT clinical advice.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "output"))

import temper_skills
from schema import AnkleInjury


def main() -> None:
    tree = temper_skills.ingest_skill(
        os.path.join(HERE, "input", "skill.md"),
        schema=AnkleInjury,
        profile="audit-grade",
        fn_name="assess_ankle",
    )
    out = os.path.join(HERE, "output", "assess_ankle.generated.py")
    tree.export(out)
    print(f"\nExported {out}\n")
    print(tree.to_source())


if __name__ == "__main__":
    main()
