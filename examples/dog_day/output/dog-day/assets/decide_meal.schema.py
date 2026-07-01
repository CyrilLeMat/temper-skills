"""DecideMeal — mini-schema for the 'next meal?' decision of the dog_day flow.

This decision is COUPLED: `just_exercised` is fed by the output of decide_walk (a walk →
the dog exercised). The orchestrator chains the two; the tree stays a pure function of its
own features.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DecideMeal(BaseModel):
    hours_since_last_meal: float
    time_of_day: Literal["morning", "midday", "evening"]
    last_meal_size: Literal["none", "light", "full"]
    just_exercised: bool = False               # ← from decide_walk's outcome
    minutes_since_exercise: float | None = None  # ← from decide_walk timing; lets the 30-min rule be measured
    had_full_meal_today: bool | None = None    # whole-day predicate for the evening skip; last_meal_size is only a fallback when None
