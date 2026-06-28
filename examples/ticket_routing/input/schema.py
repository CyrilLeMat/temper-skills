"""TicketSchema — pre-computed structured features for support-ticket routing.

A closed feature space (enums + a bounded score + a bool): unlike a toxic-food list,
there's no unbounded enumeration tail, so the adversarial loop converges — its job is
the interactions (priority × tier × SLA × security), not enumerating items.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TicketSchema(BaseModel):
    priority: Literal["low", "medium", "high", "urgent"]
    security_score: float                                   # 0..1, model-scored sensitivity
    customer_tier: Literal["free", "pro", "enterprise"]
    category: Literal["billing", "bug", "feature_request", "security", "account", "other"]
    sla_breached: bool = False
