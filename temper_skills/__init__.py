"""Temper-Skills — compile an agent's decision logic from a prompt into code."""

from .audit import FitnessReport, audit_skill
from .decompose import Decomposition, decompose_skill
from .distill import distill
from .export_skill import render_tempered_skill
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
    "audit_skill",
    "FitnessReport",
    "decompose_skill",
    "Decomposition",
    "ingest_skill",
    "recrystallize",
    "diff_trees",
    "render_tempered_skill",
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
