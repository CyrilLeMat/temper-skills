## What & why

<!-- One or two sentences: what changes, and what problem it solves. -->

## Checks

- [ ] `pytest -q` passes locally (no network needed)
- [ ] `ruff check . && ruff format --check .` and `mypy` clean
- [ ] CHANGELOG.md updated under `[Unreleased]` (skip for docs-only changes)
- [ ] If a canonical example's artifacts changed: `temper-skills validate` still passes on it
