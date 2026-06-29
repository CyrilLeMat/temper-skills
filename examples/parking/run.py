"""Temper the curbside-parking skill into a deterministic advisor.

    export ANTHROPIC_API_KEY=...   # or any provider / vertex / agent CLI
    python examples/parking/run.py
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "input"))

import temper_skills
from schema import ParkingQuery


def main() -> None:
    tree = temper_skills.ingest_skill(
        os.path.join(HERE, "input", "skill.md"),
        schema=ParkingQuery,
        profile="standard",
        fn_name="can_i_park",
    )
    out_dir = os.path.join(HERE, "output")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "can_i_park.generated.py")
    tree.export(out)
    print(f"\nExported {out}\n")
    print(tree.to_source())


if __name__ == "__main__":
    main()
