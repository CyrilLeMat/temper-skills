"""DecideVet — mini-schema for the 'does this symptom need the vet?' decision.

Independent of the other two. The Ottawa-style interactions (severity × duration × age)
make it the most genuinely combinatorial decision of the flow.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DecideVet(BaseModel):
    symptom: Literal["none", "vomiting", "limping", "lethargy", "not_eating", "other"]
    severity: Literal["mild", "moderate", "severe"]
    duration_hours: float
    age_years: float
