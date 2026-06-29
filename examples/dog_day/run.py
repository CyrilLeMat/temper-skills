"""Decompose the dog-care flow into its decision points.

    export ANTHROPIC_API_KEY=...   # or any provider / vertex / agent CLI
    python examples/dog_day/run.py

Educational example only — not veterinary advice.
"""

from __future__ import annotations

import os

import temper_skills

HERE = os.path.dirname(__file__)


def main() -> None:
    decomp = temper_skills.decompose_skill(os.path.join(HERE, "input", "skill.md"))
    print(f"\n{len(decomp.decisions)} decision(s) + {len(decomp.generative_steps)} generative step(s)\n")
    for d in decomp.decisions:
        chain = f"  (consumes {', '.join(d.consumes)})" if d.consumes else ""
        print(f"  • {d.fn_name}: {d.description}{chain}")
        print(f"      features: {[f.name for f in d.features]}  → outcomes: {d.outcomes}")
    for g in decomp.generative_steps:
        print(f"  • generative: {g}  (left to the model)")


if __name__ == "__main__":
    main()
