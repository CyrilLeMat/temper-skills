"""Temper-Skills — compile an agent's decision logic from a prompt into code."""

from .distill import distill
from .incremental import diff_trees, recrystallize
from .ingest import ingest_skill
from .sources import (
    DEFAULT_PERSONAS,
    BAD_FAITH_ACTOR,
    DOMAIN_EXPERT,
    EDGE_CASE_HUNTER,
    LITERALIST,
    OVERENGINEERING_CRITIC,
    Persona,
    Sources,
)
from .tree import DecisionNode, DecisionTree

__version__ = "0.0.1"

__all__ = [
    "distill",
    "ingest_skill",
    "recrystallize",
    "diff_trees",
    "Sources",
    "Persona",
    "DecisionTree",
    "DecisionNode",
    "DEFAULT_PERSONAS",
    "LITERALIST",
    "EDGE_CASE_HUNTER",
    "BAD_FAITH_ACTOR",
    "DOMAIN_EXPERT",
    "OVERENGINEERING_CRITIC",
]
