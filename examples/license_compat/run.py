"""Temper the license-compatibility skill into a deterministic assessor.

    export ANTHROPIC_API_KEY=...   # or any provider / vertex / agent CLI
    python examples/license_compat/run.py

Educational example only — not legal advice.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "input"))

import temper_skills
from schema import LicenseQuery


def main() -> None:
    tree = temper_skills.ingest_skill(
        os.path.join(HERE, "input", "skill.md"),
        schema=LicenseQuery,
        profile="audit-grade",
        fn_name="assess_license",
    )
    out = os.path.join(HERE, "output", "assess_license.generated.py")
    tree.export(out)
    print(f"\nExported {out}\n")
    print(tree.to_source())


if __name__ == "__main__":
    main()
