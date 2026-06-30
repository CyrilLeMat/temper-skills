#!/usr/bin/env python3
"""Gate for the temper-skills skill: is the lib installed AND is a model backend usable?

The skill reads the exit code only:
    0   ready          — package importable and a backend is available
    10  no_backend     — package importable but no usable backend
    11  not_installed  — package not importable

We test the active interpreter (importlib, not `pip show` — which can inspect the wrong
environment), then delegate the backend decision to the lib's own resolver. Reimplementing
the check (e.g. `shutil.which("claude")`) drifts from reality: auto_backend uses cli_runs(),
which *executes* the CLI to confirm it's runnable, so a CLI on PATH but not logged in counts
as no backend.
"""
import importlib.util
import sys

NOT_INSTALLED = 11
NO_BACKEND = 10
READY = 0

if importlib.util.find_spec("temper_skills") is None:
    sys.exit(NOT_INSTALLED)

from temper_skills.backends import auto_backend  # noqa: E402

try:
    auto_backend()
except RuntimeError:
    sys.exit(NO_BACKEND)
sys.exit(READY)
