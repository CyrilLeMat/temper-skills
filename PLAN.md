# Adoption plan — make temper-skills something people actually run

> **Status (2026-07-02, evening):** steps 1–4 implemented; step 5 mostly done — repo
> public with description/topics, **v0.0.1 on PyPI** (trusted publishing via release.yml,
> `uvx temper-skills` verified cold), GitHub release out, and the first ecosystem audit
> committed (docs/audits/anthropic-skills-2026-07-02.md: 17 official skills, 0 clean
> temper, 11 bundling 2–5 decisions). **Remaining:** marketplace/awesome-list submissions
> (outward PRs — need a go-ahead), the launch post itself (a community-corpus sweep would
> give it stronger `temper` verdicts than Anthropic's creative skills). B3 stays gated on
> demand.

Three initiatives, one funnel. Today the project only delivers value at the end of a long
belief chain (understand tempering → ratify a schema → run a 20-round loop → get a tree).
Each initiative moves value earlier in the chain:

```
discover ──▶ first value in 2 min ──▶ reason to return ──▶ spread
   │              │                        │
   │              │                        └── B. tests-first framing (CI hook, behavior locks)
   │              └── C. one-command start (uvx / bare audit, no config, no key)
   └── A. audit as the front door ("lint for skills" — a report worth reading on its own)
```

Ground rule carried over from the review: **packaging over machinery**. Nothing below adds
a new judged axis, persona, or backend. Feature freeze holds everywhere else until this ships.

---

## A. Reposition `audit` as the front-door product ("skill lint")

**Problem.** `audit` is built and rendered as a *gate for temper* (`verdict: temper|caveats|skip`,
internal jargon like "H4"). It only matters to someone already sold on tempering. Repositioned,
the same data is a standalone health report any skill author wants: *what decisions is this
skill making implicitly, which are ambiguous, which parts will drift?* Temper becomes one of
the recommended fixes, not the premise.

### A1. Directory fan-out — `temper-skills audit <dir>`

The `npm audit` moment: one command over a whole skill library.

- Accept a directory (or glob) in `audit` ([cli.py:501](temper_skills/cli.py)); discover
  `SKILL.md` / `*.md` skills recursively (reuse the discovery conventions the exporter
  already knows from [export_skill.py](temper_skills/export_skill.py)).
- Output a ranked one-line-per-skill table: name · decisions found · top finding ·
  recommended action. Sort by "most worth acting on" (decisiveness × stakes, descending).
- `--json` emits the list of `FitnessReport`s (the per-skill shape already exists).
- Parallelize the per-skill LLM calls (it's one judge turn each — a 50-skill library should
  finish in ~1 min, not 50).
- Exit code stays pipeline-friendly: 0 if anything is actionable, 3 if all skip.

### A2. Findings-style report — reword the rendering, not the scoring

Keep `JudgeScores`/`verdict_of`/`recommend_action` ([audit.py](temper_skills/audit.py))
untouched. Change only `_print_fitness` ([cli.py:561](temper_skills/cli.py)) to speak to a
skill author instead of the temper pipeline:

- Lead with **findings**, not scores: "makes N implicit decisions", "branches on unbounded
  free text: `food_item` — will drift call-to-call", "outcome set is finite (escalate /
  route / review) but the tie-break between X and Y is unstated".
  The raw material is already in `rationale`, `open_features`, `distinct_decisions`,
  `caveats` — this is a rendering pass.
- Each finding carries a **fix**, and temper is just one of them: `temper` → "freeze into
  code + tests", `externalize_data` → "move the list to a data file", `build_normalizer` →
  "pin these fields upstream", `delegate_prose` → "no decision here — this is a prose skill".
- Kill internal jargon in user-facing output (H4, "closure", "caveats" as a verdict name).
  Verdict words become author-facing: e.g. `freeze-worthy` / `fixable` / `leave as prose`.
- Add `--md` (or `--report out.md`): the same findings as a Markdown report — pasteable in a
  PR, shareable, and the building block for the future GitHub Action and the
  "I audited the ecosystem" launch post.

### A3. Docs re-lead

- README Step 1 stops being "is there a decision worth freezing?" (temper's question) and
  becomes "find out what your skill is silently deciding" (the author's question).
- The subagent skill's audit path gets the same reframing so `/temper <dir>` on a skills
  folder produces the table, not N sequential gate verdicts.

**Acceptance:** `uvx temper-skills audit .claude/skills/` on a stranger's real library
produces a report they'd screenshot — with zero prior knowledge of tempering.

---

## B. Lead with "tests for your skill", not "a tree"

**Problem.** "Deterministic decision tree" is the mechanism; "your skill finally has a test
suite" is the felt need — and a much bigger market. The loop *already* produces the assets
(validation dataset + behavior-lock pytest via
[export_tree.py](temper_skills/export_tree.py) — `write_dataset_and_tests`,
`render_behavior_lock`, `render_ratified`). Today they're presented as side effects of the
tree. Invert the billing.

### B1. Messaging inversion (README, SKILL.md descriptions, pyproject description)

- New headline shape: **"Adversarial reviewers write a test suite for your skill's decision
  logic — and freeze that logic into deterministic Python it must keep passing."**
  Tests are the promise; the tree is how the promise is kept cheap (zero LLM calls at
  inference, CI-pinnable).
- README's hero output block shows **the generated test file + the dataset diff first**, the
  tree second. The `✎ validation dataset` panel already in the README is the right artifact —
  promote it above the `route_ticket.py` listing.
- The two skill `description` frontmatter fields ([.claude/skills/temper-skills/SKILL.md](.claude/skills/temper-skills/SKILL.md),
  [skills/temper-skills/](skills/temper-skills/)) add the trigger phrases users actually say:
  "test my skill", "add tests to this skill", "eval my skill" — today they only trigger on
  temper/freeze/harden vocabulary.

### B2. Make the test artifacts first-class in the CLI output

- End-of-run summary leads with: `✓ 14-case test suite → test_route_ticket.py ·
  3 open disagreements to review` — then the tree path.
- `validate` output framed as "test run" (pass/fail per case) — it already is one; name it so.

### B3. (Phase 2, only after A+C ship) `temper-skills cases` — tests without the full loop

A cheaper on-ramp for people who want the tests but not (yet) the tree: run the persona
pass(es) against the skill to propose labeled cases, write the `.validation.jsonl` +
a pytest that runs the *skill's own claimed logic* is out of scope — but emitting the
dataset + a ratification checklist is not. Reuses the incremental dataset writer
([update_validation.py](temper_skills/update_validation.py)) and the existing personas;
no new machinery, just a shorter circuit. **Gate this on demand signals** (someone asks for
it) — do not build speculatively.

**Acceptance:** a user who has never heard of decision trees can read the README's first
screen and correctly say what they get ("a reviewed test suite for my skill's decisions,
plus code that passes it").

---

## C. Collapse time-to-first-value to one command

**Target:** stranger → first interesting output in under 2 minutes, no config file, no
API key decision, no schema ratification.

### C1. `uvx temper-skills audit <path>` works cold

- Verify the wheel entry point runs under `uvx` with no repo checkout (it should — hatchling
  + `[project.scripts]` are in place; test it).
- Audit must require **no schema step**: it already self-drafts via
  `propose_schema_only=True` ([audit.py:218](temper_skills/audit.py)) — keep it that way;
  never let a future change put a ratification stop in front of `audit`.
- Backend zero-config: `auto_backend` already falls back API-key → detected agent CLI
  (`claude`, `opencode`). Add one crisp error for the nothing-detected case that lists the
  three ways to get a backend in copy-pasteable form. This error message *is* onboarding —
  treat it as a first-class surface.

### C2. Bare invocation does the right thing

- `temper-skills <path>` (no subcommand) → runs `guide` (audit-first, offers next step).
  One thing to remember instead of five subcommands. Typer supports a default command with
  a small callback shim in [cli.py](temper_skills/cli.py).
- `temper-skills <dir>` → the A1 library table.

### C3. The Claude Code path is already one command — keep it honest

- `/temper <path>` with no install is the flagship on-ramp; re-verify end-to-end from a
  clean machine *after* the A/B renames land (the subagent skill vendors its own scripts —
  confirm the vendored copies pick up the new report rendering via the existing
  sync tests: [test_vendor_scripts_sync.py](tests/test_vendor_scripts_sync.py),
  [test_skill_docs_sync.py](tests/test_skill_docs_sync.py)).

### C4. README quickstart inversion

First code block in the README becomes:

```bash
uvx temper-skills audit path/to/skill.md     # or: /temper path/to/skill.md in Claude Code
```

Everything else (profiles, schemas, backends, Vertex) moves below the fold.

**Acceptance:** screen-recorded cold start — `uvx temper-skills audit` on a public skill —
under 2 minutes including install, no environment prep beyond an existing `claude` login
or API key.

---

## Sequencing

| Order | What | Why first |
| --- | --- | --- |
| 1 | C1 + C4 (cold-start + quickstart) | Cheapest; everything else is pointless if the first run fails |
| 2 | A1 + A2 (fan-out + findings rendering) | The discovery wedge and the launch-content generator |
| 3 | B1 + B2 (tests-first messaging) | Pure copy/rendering; do alongside A2 |
| 4 | C2, C3, A3 | Polish on the paths above |
| 5 | **Publish** (GitHub public, PyPI, marketplaces) + the "audited N popular skills" post | The actual goal — everything above exists to make this land |
| — | B3 (`cases` command) | Only on demand signal, post-launch |

## Explicitly out of scope (so this doesn't become feature work)

- No new judged axes, personas, profiles, or backends.
- No smarter audit scoring — rendering and reach only.
- No SkillClaw integration build (lightweight courtship only: publish audit results over a
  public library, open a discussion on their repo pointing at `--json`).
- No GitHub Action yet — `--md` report output in A2 is its building block; the Action is a
  post-launch project.
