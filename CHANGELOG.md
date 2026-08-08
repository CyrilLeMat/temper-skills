# Changelog

Notable changes. Format follows [Keep a Changelog](https://keepachangelog.com/);
versions follow [SemVer](https://semver.org/) (pre-1.0: minor bumps may break).

## [Unreleased]

## [0.1.0] — 2026-08-08

First minor release: the mechanics have been stable across 0.0.x; this bump
reflects that (SemVer pre-1.0: minors may still break).

### Added
- Community scaffolding: issue templates (bug / feature), a PR checklist template,
  and a Contributor Covenant 2.1 code of conduct. README gained a banner
  (`docs/assets/banner.png` — also meant for the repo's social preview).
- CI now enforces `ruff format` (whole repo reformatted once; generated dirs
  excluded) and `mypy` over `temper_skills/` — `ingest_skill` gained `@overload`s
  so its return type follows `propose_schema_only`, and `loop_error` became a
  declared `DecisionTree` field.

### Fixed
- Fresh installs no longer require a Rust toolchain on macOS: litellm capped
  `<1.92` — from 1.92 it ships a Rust extension with Linux/Windows wheels only
  (1.91.4 is the last pure-Python release), so macOS pip fell back to an sdist
  build that dies without cargo. Cap lifts when litellm publishes macOS wheels.
- `temper_skills.__version__` no longer drifts from the released version: it
  was a hand-maintained literal stuck at "0.0.1"; now read from package
  metadata (`importlib.metadata`).
- CI lint no longer breaks on ruff releases: the action installed latest ruff,
  whose defaults grew (0.16 turned a green tree red and started reformatting
  Markdown code blocks). The rule set is now pinned in `[tool.ruff.lint]`,
  `*.md` is excluded (README excerpts are verbatim generated output), and the
  CI action pins `version: 0.16.2`.
- The PyPI project page now renders correctly: README image and doc/example links
  were repo-relative (broken image, 404 links on pypi.org) — all rewritten to
  absolute GitHub URLs; `Documentation` added to `[project.urls]`.
- Audit verdicts no longer flip across identical runs: `ApiBackend` pins
  `temperature=0` (constructor knob to override). The determinism exposed two
  judge biases, both fixed by tightening the prompts: `distinct_decisions` now
  counts OUTPUTS, not rules (a pile of overrides selecting one route is ONE
  decision — ticket_routing/parking/license_compat no longer misread as
  DECOMPOSE), and the schema proposer must spell closed vocabularies as
  `one of "a", "b", "c"` so schema closure stops depending on wording luck.
  All six README example labels re-verified live (2× each, Claude on Vertex).
  The agent-CLI path has no sampling knob — noted in `agent_cli.py`.
- A `vertex_ai/*` model without the `[vertex]` extra now fails fast at backend
  construction with install guidance, instead of surfacing four retries later
  as a raw `InstructorRetryException` traceback.

## [0.0.3] — 2026-07-03

### Fixed
- Subagent SKILL.md drift: the harvest instruction told the orchestrator to exclude
  only the `overengineering_critic` from validation-case collection, while the
  library excludes all three structural critics. The prose now matches; a generated
  "Loop invariants" fact card (earn-a-branch window, harvest exclusions, statuses,
  the gate) plus `test_skill_prose_sync.py` pin the narrative's algorithmic claims
  to `distill.py` so this class of drift fails CI.
- A backend failure after round 1 no longer masquerades as convergence: the loop
  still keeps the best tree so far, but records `loop_error` on the result — shown
  as a warning in the CLI and exposed in the `--json` manifest (agents must not
  read such a run as converged).
- Agent-CLI backend: a timed-out or transiently failing CLI call now gets the same
  corrective retry as invalid JSON, instead of bypassing the retry path entirely.

### Changed
- Internal: the validation-case row shape is now defined once in
  `validation_case.py` (stdlib-only, vendored with the exporters) and constructed
  through it in distill/export_tree/skill_render — same on-disk JSONL shape and key
  order as before. The loop's two scoring semantics got named types (`AdoptKey`:
  parsimony tie-break for adopting a round's attempt; `SelectKey`: panel-mean
  tie-break for plateau detection and final selection), with tests pinning the
  difference. The vendored-scripts guard now also imports every vendored module
  standalone, not just text-checks it.
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

[Unreleased]: https://github.com/CyrilLeMat/temper-skills/compare/v0.0.3...HEAD
[0.0.3]: https://github.com/CyrilLeMat/temper-skills/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/CyrilLeMat/temper-skills/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/CyrilLeMat/temper-skills/releases/tag/v0.0.1
