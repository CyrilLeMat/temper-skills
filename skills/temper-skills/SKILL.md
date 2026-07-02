---
name: temper-skills
description: Give an agent skill's decision logic a test suite and a deterministic implementation — a labeled validation dataset plus versionable Python — by driving the installed temper-skills CLI (never reimplementing the logic in prose). Use in agents without a native subagent primitive (Cursor, Hermes, generic tools) when the user wants to test, eval, audit, temper, freeze, or harden the routing/decision logic of a prompt, skill.md, or playbook ("test my skill", "what is this skill deciding?"), including auditing a whole skills directory; requires `pip install temper-skills` and a model backend (a logged-in claude/opencode CLI or an API key). Not for continuous scoring, text generation, or logic with no documentation the model can reach.
license: Apache-2.0
allowed-tools: Bash, Read, Write
metadata:
  author: hellosunrise
  version: "0.1.0"
---

# Temper-Skills (library mode)

Turn the decision logic of an agent skill or prompt into deterministic Python — zero LLM
calls at inference — by **driving the installed `temper-skills` CLI**. You orchestrate the
CLI and relay its output; the library does the tempering. You never write the decision tree
yourself.

> Use this skill when you do **not** have a native subagent/Task primitive to run the loop
> yourself. Inside Claude Code, prefer the subagent-mode skill (it runs keyless, with a live
> panel). This mode shells out to the CLI instead.

## When to use

- A `.md` skill, system prompt, or playbook holds routing/decision logic (if-this-then-that
  over structured inputs) that should be testable, diffable in a PR, or resilient to model
  updates.
- Good fit: ticket routing, classification rules, eligibility checks — categorical decisions
  over pre-computable features.
- **Not** a fit: continuous scoring, text generation, or logic with no documentation the
  model can reach.

## Non-negotiable rules

1. **Always call the library through its CLI. Never reimplement the decision logic in natural
   language** as a substitute for running it.
2. **Never skip schema ratification.** The schema you approve is the *naive seed* the loop then
   co-evolves (the `schema_critic` grows it, the earn-a-branch guard prunes it), so a silent
   extraction error in the seed still poisons everything. Use the file-based gate below
   (`--propose-schema`), even when no terminal is attached. Review the co-evolved schema and any
   `schema gaps` / `schema grew` notes the CLI prints at the end.
3. **Never install silently.** If the gate (Step 0) reports the lib or a backend is missing,
   ask the user before running `pip install` or changing their environment.
4. **Never claim the tree is "correct"** — only that it is deterministic and auditable.
   Correctness is the user's, established by ratified examples (`validate`, Step 4).
5. **Relay the CLI's gates and verdicts verbatim** — audit verdict, persona panels, gray
   zones, cases awaiting ratification. Do not summarize them away.

## Step 0 — Check install + backend

Run `python scripts/check_install.py` and branch on the exit code:

- `0` — ready, proceed.
- `10` — installed but **no model backend**. Tell the user: temper-skills needs a backend —
  a logged-in `claude` or `opencode` CLI, or `ANTHROPIC_API_KEY` in the environment. Ask how
  they want to provide one. Do not proceed until a backend exists.
- `11` — **not installed.** Ask: "temper-skills is not installed. Install it now?
  (`pip install temper-skills`)" Install only on explicit confirmation.

## Step 1 — Triage with `guide` (lead here)

Find the `.md` file or prompt holding the decision logic (confirm the path with the user if
ambiguous), then run the one-command tour:

```bash
temper-skills guide <path/to/skill.md> --json
```

**If the user points at a directory** (a skill library), sweep it instead of guiding one file —
the audit is a report worth relaying on its own:

```bash
temper-skills audit <dir> --json --report audit.md
```

Relay the ranked findings (the JSON is a list of per-skill reports, most actionable first) and
offer to `guide` the top pick. `audit.md` is a shareable Markdown version for a PR.

**Always pass `--json`.** `guide` and `ingest` then emit a machine-readable manifest on
**stdout** and send the human Rich panels to **stderr** — read the manifest, do not scrape the
panels. `guide`'s manifest is:

```json
{ "audit": { "verdict": "...", "recommended_action": "...", ... },
  "action_taken": "temper|decompose|...",
  "status": "compiled|stopped_for_ratification|action_not_auto_run",
  "final_skill_path": "...", "artifacts": ["..."] }
```

`guide` **audits** the skill, then follows `recommended_action`. Relay the audit verdict and
action to the user:

- `temper` — one tree-shaped decision. `guide` tempers it (quick); `status: compiled`.
- `decompose` — a flow (≥2 decisions). `guide` emits per-decision schemas and stops;
  `status: stopped_for_ratification`.
- `externalize_data` / `build_normalizer` / `delegate_prose` — not tempering jobs.
  `status: action_not_auto_run`; relay the action hint and stop.

`guide` is the tour: it runs the `quick` profile and auto-accepts the inferred schema. That is
fine for "show me what this does," **but for a tree the user will rely on, go to Step 2** so
the schema is ratified.

## Step 2 — Produce a keeper tree (ratified flow)

### 2a. Draft the schema and STOP for ratification

```bash
temper-skills ingest <path/to/skill.md> --propose-schema --json
```

This writes `schema.proposed.py` and stops — the loop never runs on an unratified schema. The
JSON on stdout gives you `{proposed_schema_path, fn_name, features:[{name,type,description}],
constraints}`. Show the user the proposed features and ask exactly one thing: **accept these
features, or edit the list?** Apply their edits to `schema.proposed.py`.

Do **not** ask the user anything else here — not feature breadth, not which branches to keep.
Pruning is the loop's job (the overengineering critic), not the user's.

### 2b. Compile against the ratified schema

```bash
temper-skills ingest <path/to/skill.md> \
  --schema schema.proposed.py \
  --profile standard \
  --json
```

Pick the profile with the user — `quick | standard | audit-grade`, default `standard`; see
`references/profiles.md` before recommending. `--json` implies non-interactive: the loop runs
to convergence (it cannot pause for a per-round gate when driven this way — that gate is a
human-terminal feature) and emits the result manifest on stdout. Read that, don't scrape the
panels. (`--require-fit` aborts early with exit 3 if the audit verdict is `skip`; add it to
avoid burning the loop on a bad fit.)

### 2c. If the action was `decompose`

A flow must be split first; temper each decision separately:

```bash
temper-skills decompose <path/to/skill.md> --temper-each --out-dir out/
```

This emits one schema per decision and **stops for ratification**. Surface the schemas, let
the user edit them, then re-run the same command to compile each into a tree plus the
orchestrator skill (`--yes-unratified` skips the stop — avoid it unless the user asks).

## Step 3 — Report the artifacts (from the manifest)

The `ingest --json` manifest is the source of truth — read these fields, don't scrape:

```json
{ "tree_path": "...", "tempered_skill_path": "...",
  "validation_dataset_path": "..." , "validation_case_count": 0,
  "gray_zones": [{"node": 1, "condition": "...", "note": "..."}],
  "features": ["..."], "node_count": 0, "profile": "...", "cost_usd": 0.0 }
```

Surface all three artifacts to the user:

- `tree_path` — the decision tree: imports nothing, zero LLM calls at inference, with a
  `generated_at` + model header and per-node provenance comments;
- `tempered_skill_path` — the **tempered `skill.md`**: the original skill rewritten to *call*
  the frozen tree instead of re-deciding. Half the deliverable; don't drop it;
- `validation_dataset_path` — the committed `.validation.jsonl` the loop built for its gray zones,
  **awaiting ratification** (`validation_case_count`). Rows with `"agrees": false` are the
  highest-value disagreements for the user to rule on. The behavior-lock tests beside it
  (`test_<stem>.py`) stay green; only ratified labels can turn a test red.

Tell the user the paths, the profile, the `cost_usd`, and the `gray_zones`. Restate rule 4:
deterministic and auditable, not "correct."

## Step 4 (optional) — Pin it in CI

Once the user has ratified a labeled set, validate the tree against it:

```bash
temper-skills validate decision_tree.generated.py ratified.json --min-agreement 1.0
```

Non-zero exit on disagreement — this is what pins the tree in CI. Each disagreement is either
a tree bug or a mislabeled example; relay them for sign-off.

## Reference

See `references/profiles.md` for rounds / convergence / persona panel / cost per profile
before recommending one.

## Never

- Never write the tree's logic in natural language instead of running the library.
- Never skip schema ratification, even in a `quick` demo (`quick` drops provenance comments,
  not the gate).
- Never install or modify the environment without explicit confirmation.
- Never claim the generated tree is "correct."
