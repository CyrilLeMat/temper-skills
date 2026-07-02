# Changelog

Notable changes. Format follows [Keep a Changelog](https://keepachangelog.com/);
versions follow [SemVer](https://semver.org/) (pre-1.0: minor bumps may break).

## [Unreleased]

### Changed
- Internal: compile orchestration extracted from the CLI into `pipelines.py`
  (`compile_tree`, `write_validation_artifacts`, `tree_manifest`, `load_schema`) —
  one code path now backs `ingest`, `guide`/`audit`'s temper, and
  `decompose --temper-each`; importable without typer/Rich. The CLI no longer
  mutates a module-global console (each command owns its UI surface), which also
  fixes `decompose --json` mixing panels into the stdout manifest.

## [0.0.2] — 2026-07-02

### Fixed
- `ApiBackend`: concurrent first calls raced instructor's lazy provider/mode
  registration ("Available modes: []") — the fan-out in `audit <dir>` hit it on
  16/17 skills. First call is now serialized, then fully concurrent.
- `audit --json`: human console lines could corrupt the JSON stream on stdout;
  panels now go to stderr (same contract as `ingest`/`guide`).
- `[vertex]` extra now installs `google-cloud-aiplatform` — litellm's
  `vertex_ai/*` route imports `vertexai`, so the documented setup actually works.

### Added
- Ruff lint in CI; Python 3.10–3.13 test matrix; `py.typed` marker; PyPI
  classifiers (incl. Python versions) and project URLs; Dependabot;
  CONTRIBUTING/SECURITY; this changelog.

## [0.0.1] — 2026-07-02

First public release — on [PyPI](https://pypi.org/project/temper-skills/).

### Added
- `audit` — author-facing findings report for a skill's decision logic; single
  skill or a whole library (ranked sweep, `--report` Markdown output, `--json`).
- `temper` loop (`ingest` / `distill()`) — adversarial persona reviewers write a
  labeled validation dataset + behavior-lock pytest; the decision logic is frozen
  into a deterministic Python tree (zero LLM calls at inference).
- `decompose` — split a flow-shaped skill into per-decision mini-schemas + a thin
  orchestrator; `validate` — pin a tree against a labeled set in CI;
  `incremental` — re-crystallize an existing tree against new constraints.
- Two distribution modes: keyless subagent skill for Claude Code (`/temper`), and
  the CLI/library on any LiteLLM backend (Anthropic, OpenAI, Vertex AI, local).
- Bare invocation: `temper-skills <dir>` sweeps a library, `temper-skills <file>`
  runs the guided tour.
- First ecosystem audit: all 17 skills in anthropics/skills
  (`docs/audits/anthropic-skills-2026-07-02.md`).

[Unreleased]: https://github.com/CyrilLeMat/temper-skills/compare/v0.0.2...HEAD
[0.0.2]: https://github.com/CyrilLeMat/temper-skills/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/CyrilLeMat/temper-skills/releases/tag/v0.0.1
