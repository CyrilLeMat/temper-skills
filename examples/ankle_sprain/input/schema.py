"""AnkleInjury — features for sprained-ankle first-aid guidance.

⚠️ Educational example, NOT clinical advice.

Combinatorial public-health domain: the Ottawa Ankle Rules alone are 5 interacting
criteria (fracture screening), layered with sprain grade × time-since-injury × age.
Closed feature space → the loop converges, and it surfaces the "oh merde" edge: RICE is
outdated (since ~2012) — POLICE / PEACE & LOVE replace it, and prolonged ice slows healing.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class AnkleInjury(BaseModel):
    pain_malleolar_zone: bool                       # pain over the ankle bones
    bone_tenderness_lateral_malleolus: bool = False # Ottawa criterion
    bone_tenderness_medial_malleolus: bool = False  # Ottawa criterion
    can_bear_weight: bool = True                    # able to take 4 steps
    visible_deformity: bool = False                 # gross deformity → emergency
    sprain_grade: Literal["mild", "moderate", "severe"] = "mild"
    hours_since_injury: float | None = None
    age_years: int | None = None
    patient_profile: Literal["active", "sedentary"] = "active"
