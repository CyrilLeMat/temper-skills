"""Temper the ticket-triage skill into a deterministic router.

    export ANTHROPIC_API_KEY=...   # or any provider / vertex / agent CLI
    python examples/ticket_routing/run.py
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "output"))

import temper_skills
from schema import TicketSchema


def main() -> None:
    tree = temper_skills.ingest_skill(
        os.path.join(HERE, "input", "skill.md"),
        schema=TicketSchema,
        profile="standard",
        fn_name="route_ticket",
    )
    out = os.path.join(HERE, "output", "route_ticket.generated.py")
    tree.export(out)
    print(f"\nExported {out}\n")
    print(tree.to_source())


if __name__ == "__main__":
    main()
