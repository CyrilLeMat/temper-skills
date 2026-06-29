"""ParkingQuery — pre-computed structured features for the curbside parking advisor.

A closed feature space (enums + a bounded hour + two bools): unlike a toxic-food list,
there's no unbounded enumeration tail, so the adversarial loop converges. Its job is the
*interactions* (zone × day × hour × holiday × permit), not enumerating items.

The features are RAW observables — the zone painted on the curb, the day, the clock hour,
whether it's a public holiday, whether the driver holds a permit. The tree DERIVES "is the
meter enforced right now" from them; we don't hand it a presupposed `meter_active` flag.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ParkingQuery(BaseModel):
    zone_type: Literal["unrestricted", "metered", "residential_permit", "no_stopping"]
    day: Literal[
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
    ]
    hour: int                              # 0..23, local clock, start of the hour
    is_public_holiday: bool = False
    has_resident_permit: bool = False
