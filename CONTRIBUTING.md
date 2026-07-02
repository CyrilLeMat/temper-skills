# Contributing

Thanks for looking! Issues and PRs welcome — small, focused PRs merge fastest.

## Dev setup

```bash
pip install -e ".[dev]"
git config core.hooksPath .githooks   # once per clone: pre-commit runs the suite
pytest -q                             # full suite, no network
ruff check temper_skills tests        # lint (CI-enforced)
```

## Ground rules

- **Tests come with the change.** The suite runs without network — model calls are
  faked (see `tests/conftest.py`); CI gates at 90% coverage across Python 3.10–3.13.
- **The audit rubric is pinned.** Thresholds in `temper_skills/audit.py`
  (`verdict_of`, `recommend_action`) are deliberate judgement calls locked by
  `tests/test_audit.py` — changing them must show up as a reviewed diff there.
- **Generated artifacts are dogfooded.** CI re-validates the example trees against
  their datasets (`temper-skills validate`); regenerate outputs rather than
  hand-editing them.
- Comment sparingly — genuine "why", not narration. Match the style around you.

## Releases (maintainer)

Bump `version` in `pyproject.toml`, update `CHANGELOG.md`, tag `vX.Y.Z`, push the
tag — `release.yml` tests, builds, and publishes to PyPI via trusted publishing.
