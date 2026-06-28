"""Backend abstraction: how one structured LLM turn is executed.

`distill()` is backend-agnostic — it only ever calls `backend.complete(system,
user, schema)` and gets back a validated Pydantic object. Whether that turn runs
against the metered API or a subscription agent CLI is the backend's concern.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class Backend(ABC):
    name: str = "backend"

    def __init__(self, model: str):
        self.model = model
        self.input_tokens = 0
        self.output_tokens = 0

    @abstractmethod
    def complete(self, system: str, user: str, schema: type[T]) -> T:
        """Run one turn and return a validated instance of ``schema``."""

    def cost_estimate(self) -> float | None:
        """USD cost of calls so far, or None when billing isn't metered here."""
        return None

    def describe(self) -> str:
        return f"{self.name} ({self.model})"
