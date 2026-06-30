---
name: temper-skills
description: Compile an agent's decision logic — a prompt, skill.md, or playbook — into a deterministic, auditable Python decision tree by driving the installed temper-skills CLI (never reimplementing the logic in prose). Use in agents without a native subagent primitive (Cursor, Hermes, generic tools) when routing/decision logic needs to be tested, versioned in a PR, or made independent of model updates; requires `pip install temper-skills` and a model backend (a logged-in claude/opencode CLI or an API key). Not for continuous scoring, text generation, or logic with no documentation the model can reach.
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
2. **Never skip schema ratification.** The inferred schema caps what the tree can express; a
   silent extraction error poisons everything. Use the file-based gate below (`--propose-schema`),
   even when no terminal is attached.
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
temper-skills guide <path/to/skill.md>
```

`guide` **audits** the skill, then follows the recommended action and prints the result. Relay
its output verbatim — especially the **audit verdict** and **recommended action**:

- `temper` — one tree-shaped decision. `guide` tempers it (quick, frictionless).
- `decompose` — a flow (≥2 decisions). `guide` splits it and stops for ratification.
- `externalize_data` / `build_normalizer` / `delegate_prose` — `guide` will **not** auto-run
  these; relay the action hint and stop. These are not tempering jobs.

`guide` is the tour: it runs the `quick` profile and auto-accepts the inferred schema. That is
fine for "show me what this does," **but for a tree the user will rely on, go to Step 2** so
the schema is ratified.

## Step 2 — Produce a keeper tree (ratified flow)

### 2a. Draft the schema and STOP for ratification

```bash
temper-skills ingest <path/to/skill.md> --propose-schema
```

This writes `schema.proposed.py` and stops — the loop never runs on an unratified schema.
Show the user the proposed features (name + type + meaning) and ask exactly one thing:
**accept these features, or edit the list?** Apply their edits to `schema.proposed.py`.

Do **not** ask the user anything else here — not feature breadth, not which branches to keep.
Pruning is the loop's job (the overengineering critic), not the user's.

### 2b. Compile against the ratified schema

```bash
temper-skills ingest <path/to/skill.md> \
  --schema schema.proposed.py \
  --profile standard \
  --yes
```

Pick the profile with the user — `quick | standard | audit-grade`, default `standard`; see
`references/profiles.md` before recommending. `--yes` runs the loop to convergence without
blocking on a terminal **the panels still print** — relay them. (`--require-fit` will abort
early with exit 3 if the audit verdict is `skip`; add it to avoid burning the loop on a bad
fit.)

### 2c. If the action was `decompose`

A flow must be split first; temper each decision separately:

```bash
temper-skills decompose <path/to/skill.md> --temper-each --out-dir out/
```

This emits one schema per decision and **stops for ratification**. Surface the schemas, let
the user edit them, then re-run the same command to compile each into a tree plus the
orchestrator skill (`--yes-unratified` skips the stop — avoid it unless the user asks).

## Step 3 — Report the artifacts

`ingest` writes three things — surface all of them:

- the decision tree (`decision_tree.generated.py` by default) — imports nothing, zero LLM
  calls at inference, with a `generated_at` + model header and per-node provenance comments;
- the **tempered `skill.md`** (`<out>.tempered.md`) — the original skill rewritten to *call*
  the frozen tree instead of re-deciding. This is half the deliverable; don't drop it;
- `<out>.proposed_examples.json` — cases the loop drafted for its gray zones, **awaiting
  ratification**. Flag any whose proposed label differs from what the tree returns; those are
  the highest-value disagreements for the user to rule on.

Tell the user the output paths, the profile used, and any unresolved gray zones flagged in the
tree's comments. Restate rule 4: deterministic and auditable, not "correct."

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
