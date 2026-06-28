"""DogFoodQuery — the pre-computed structured features the tree branches on (§11.2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DogFoodQuery(BaseModel):
    food_item: str                                  # "peanut butter", "grapes", "chocolate"
    food_form: Literal["standard", "low_fat", "cooked", "raw", "concentrated"] = "standard"
    dog_weight_kg: float                            # influences dose-dependent toxicity
    dog_breed: str | None = None                    # some breeds have specific sensitivities
    quantity_grams: float | None = None             # for dose-dependent items (e.g. chocolate)
