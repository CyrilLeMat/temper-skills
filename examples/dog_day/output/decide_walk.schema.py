"""DecideWalk — mini-schema for the 'walk the dog now?' decision of the dog_day flow.

Proposed by `temper-skills decompose --emit-schemas`, then ratified. One decision, one
bounded feature set — the unit temper actually freezes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DecideWalk(BaseModel):
    hours_since_last_walk: float
    weather: Literal["clear", "rain", "storm", "heat"]
    dog_energy: Literal["low", "normal", "high"]
    owner_available: bool = True
    is_late: bool = False                      # past the dog's usual last-walk hour
