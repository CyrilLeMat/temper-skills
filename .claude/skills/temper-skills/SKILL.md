---
name: temper-skills
description: Compile an agent's decision logic (a prompt or skill.md) into a deterministic, versionable Python decision tree via an adversarial multi-persona loop — run entirely on your Claude Code subscription using subagents, no API key. Use when the user wants to "temper", "distill", "freeze", or "harden" the routing/decision logic of a skill, prompt, or playbook into testable code, or asks to turn a skill.md into a decision tree.
---

# Temper-Skills (subagent mode)

Turn the decision logic living in a prompt/`skill.md` into a **deterministic Python
decision tree** — readable, diffable in a PR, zero LLM calls at inference. You (the
orchestrator) act as the **proposer**; **persona subagents** are the adversarial
reviewers. Everything runs on the user's Claude Code subscription via the Task tool.

> "Adversarial" here means **decision robustness** — challenging business logic — not
> security scanning. The loop measures internal consistency, not correctness against the
> world; real correctness still comes from the user's ratified examples.

## Operating rule — run autonomously (read this first)

**You make the decisions; the loop is the point.** There are **exactly two** moments you
may block the user, and no others:

1. **Schema accept/edit** — once, up front (the inferred features cap what the tree can express).
2. **The per-round gate** — Continue / Stop / Abort (skipped on `quick`).

For **everything else, decide and record — do not ask.** Specifically, **never** raise an
`AskUserQuestion` / multiple-choice modal to have the user choose feature breadth, whether
to keep/drop a branch, how to resolve a gray zone, or any "which design do you prefer"
question. Those are the loop's job: the `overengineering_critic` prunes complexity, and you
resolve gray zones with the safest defensible default and **record** them (see Gray zones).
The user ratifies by *reviewing* recorded provenance, not by answering questions mid-run. If
you catch yourself about to open a question modal for anything other than the two gates
above: stop, make the defensible call, record it, and keep going.

## Inputs

- A target `skill.md` / prompt (the logic to migrate), path given by the user.
- A **schema**: the pre-computed structured features the tree may branch on. If the user
  doesn't supply one, infer it from the skill (feature name + type + one-line meaning).
- Optional `hard` constraints (non-negotiable rules) and a few ratified examples.

Branch only on schema features. Conditions are valid Python boolean expressions over the
feature names (e.g. `food_item == "chocolate"`) and must be **None-safe** — any feature may
be absent at inference, so guard before comparing (`x is not None and x < 1`, never bare
`x < 1`) and coerce strings (`(s or "").strip().lower()`). A condition must never raise on a
missing feature.

Keep the inferred schema **tight**. Drop features that are circular (a feature that *is* the
answer, like `is_known_toxic_food`) or that the source skill never implies (`dog_age_years`
for a skill that doesn't mention age). A bloated schema gives the loop infinite surface and
it won't converge — the schema is the ceiling (§2.5).

### The one pre-loop human decision: the schema (accept or edit)

When you infer the schema, present it and ask exactly one thing: **"Accept these features,
or edit the list?"** That's the only legitimate pre-loop gate (§11.4) — the schema caps
what the tree can ever express, and a silent extraction error would poison everything.

**Do NOT ask the user anything else here.** In particular, do **not** ask them to choose
the feature-set *breadth*, whether to include dose/weight/form branches, or whether to
"let the critic collapse." That is the loop's job, not the user's:

- **Seed the loop with the full inferred feature set.** Let the proposer branch on whatever
  it judges relevant.
- **The `overengineering_critic` prunes** features and branches a thin skill doesn't justify
  — that is its entire purpose. Offloading that judgment to the user defeats the tool.

So the human touchpoints are exactly two: (1) accept/edit the schema, once, up front; and
(2) the per-round Continue / Stop / Abort gate below. Nothing else is a question for them.

## The personas

Four attackers plus one always-on counterweight. Spawn **one subagent per persona each
round**, in parallel (one message, multiple Task calls). Keep each subagent prompt **lean
and self-contained** — do not make them read this skill or the repo.

| persona | angle |
|---|---|
| `literalist` | exploits literal ambiguities in the schema/conditions (casing, synonyms, None) |
| `edge_case_hunter` | seeks rare combinations of feature values the tree mishandles |
| `bad_faith_actor` | tries to strategically circumvent the rules |
| `domain_expert` | tests with rare-but-plausible domain cases; mobilizes public domain knowledge |
| `overengineering_critic` | **always on** — challenges every node: is this branch real domain complexity or loop richness? would an expert hand-write it? |

Each persona subagent returns ONLY this JSON:
```json
{"persona": "<name>", "score": 0-10, "verdict": "ok|missing_case|collapsible|contradiction",
 "detail": "<one sentence>", "proposed_case": "<concrete feature assignment it mishandles, or null>",
 "proposed_tests": [{"input": {<feature: value>}, "expected": "<best-guess outcome>", "rationale": "<one line>"}]}
```

`proposed_tests` is how the validation set gets built (see below). **Every persona except
`overengineering_critic` must add a case here whenever it finds a flaw** — a full feature
assignment plus the outcome it believes correct. Tell each subagent these are proposals a
human will ratify, not ground truth. The `overengineering_critic` always returns
`proposed_tests: []` — it removes complexity, it doesn't add cases.

**`score` is always the TREE's robustness from your angle — 0 = the tree fails badly
through your lens, 10 = solid, nothing to add.** It is NOT how successful your attack
was: a persona that finds no weakness scores the tree *high* (≈9–10) and returns
`verdict: "ok"`, `proposed_case: null`. Tell every persona subagent this explicitly so
the scale is uniform across the panel.

## The loop

1. **Draft** the initial tree yourself (proposer) from the skill + schema + constraints.
   Cover obvious cases. Where the source **underdetermines** an answer (a genuine gray
   zone — e.g. "the skill says 'when in doubt, say no' but never lists safe foods"),
   **resolve it yourself with the safest defensible default** consistent with the HARD
   constraints and the source's stated bias, and **record it as a `gray_zone`** on the
   node. Do **not** stop to ask the user how to resolve it — see "Gray zones" below.
2. **Critique** — spawn the 5 persona subagents in parallel with the current tree; collect
   their scored JSON verdicts.
3. **Arbitrate** (proposer) — for each persona decide `kept` / `changed` / `rejected` with a
   one-line rationale (this is the *arbitrage log*). Then revise the tree: add a branch only
   if a critique justifies it AND an expert would write it by hand; collapse branches the
   `overengineering_critic` flags. Never contradict a HARD constraint. Track
   `rounds_survived` per node (matched by condition).
4. **Show the round panel** — round N, per-persona `score/10` (sorted worst-first), the
   arbitrage log, current tree preview, and `min/mean` score.
5. **Gate** — ask the user: Continue · Stop and review · Abort. (Skip the gate only if they
   asked for an unattended/quick run.)
6. **Converge** — stop when **every persona scores ≥ 8 AND no new gray zone appeared** for
   the round, or the user stops, or you hit the round cap (`quick` ~8, `standard` ~20).

### Build the validation set as you go (always — even with no input examples)

Every round, harvest the `proposed_tests` from each persona EXCEPT the
`overengineering_critic`, and accumulate them across all rounds into one set — **deduped by
input, dropping any input that matches a ratified example.** This is the validation set; it
is built from the panel's own findings, so it always exists even when the user supplied no
examples. Keep a running accumulator (input → case) so the same case found in two rounds
counts once. Record which persona/round each came from.

These are **proposals, not ground truth.** You are extending the validation set, not grading
your own work: never treat a label the panel authored as a ratified anchor, and never let it
gate anything. Emit the accumulated set in `tree.json` under `proposed_examples` (each case:
`input` / `expected` / `rationale`, optionally `source` — the deterministic exporter computes
what the tree returns and tags them `"status": "proposed"`). At export you surface them for
the user to ratify: they review each label, fix any that are wrong, and set
`"status": "ratified"` (or fold the case into their validation set) — only then does it gate
CI and anchor that cell on a re-run. Do **not** ask the user to ratify mid-run; it's a
review-the-output step, like gray zones.

### Gray zones are recorded, not interrogated

A gray zone is where the source genuinely underdetermines the answer. The plan resolves
these by **recording them and signing off at review** (§2.5, §4.4) — they appear as
`# gray_zone:` comments in the exported tree. So:

- **Resolve each gray zone yourself** with the safest defensible default (honor the
  source's bias — e.g. "when in doubt → no" means a conservative, minimal positive set),
  and record it as the node's `gray_zone`.
- **Never raise a blocking question to resolve a gray zone**, and never batch a list of
  design questions. The user ratifies or overrides by reading the recorded gray zones at
  the round gate or in the final output — that is the sign-off.
- The **only** blocking interactions in the whole run are: (1) the one-time schema
  accept/edit, and (2) the per-round Continue / Stop / Abort gate. If you're about to ask
  the user anything else, stop — make the defensible call, record it, and surface it.

## Export (deterministic — no LLM)

When the loop ends, write the tree to JSON and run the deterministic exporters — **both
of them**. The first emits the decision tree; the second closes the loop by emitting a
**tempered `skill.md`** that delegates the decision to that tree (the whole point: the
original prompt should now *use* the frozen logic, not re-derive it):

```bash
python -m temper_skills.export_tree  tree.json route.py
python -m temper_skills.export_skill tree.json route route.tempered.md <original_skill.md>
```

Show the user both artifacts and what changed: the original skill re-decided every call;
the tempered skill extracts features, calls `route.<fn>`, and relays the verdict — decision
frozen, model still does NL extraction + phrasing (§2.5).

If `tree.json` carries `proposed_examples`, `export_tree` also writes
`route.proposed_examples.json` (each case stamped with the tree's own prediction and
`"status": "proposed"`). Show these to the user as **cases awaiting ratification**, flagging
any whose proposed label differs from what the tree returns — those are the highest-value
disagreements to rule on.

`export_skill` is the deterministic template (default). If the user wants a **woven**
variant that reads in the original skill's own voice, you may instead rewrite the original
prose yourself — preserving its role/tone, deleting only the decision logic, and inserting
the same delegation contract (extract features → call `route.<fn>` → relay verdict, never
override; surface the recorded gray zones). Do not invent new rules; only re-route to the tree.

The tree JSON shape:
```json
{
  "fn_name": "can_dog_eat",
  "features": ["food_item", "food_form", "dog_weight_kg"],
  "default_outcome": "unknown — verify manually",
  "model": "claude-<model> via claude-code-subagents",
  "profile": "standard",
  "nodes": [
    {"condition": "food_item == \"chocolate\"", "outcome": "toxic — never",
     "rounds_survived": 14, "sources": ["domain_expert", "constraints#1"],
     "gray_zone": null, "critic_note": null}
  ],
  "proposed_examples": [
    {"input": {"food_item": "macadamia"}, "expected": "toxic — never",
     "rationale": "pins the nut gray zone the skill never lists"}
  ]
}
```

`proposed_examples` is optional and **proposals only** — `input` / `expected` / `rationale`
per case; the exporter adds the tree's prediction and `"status": "proposed"`. Omit the key
if the existing ratified examples already pin every contested cell.

The exported `route.py` carries a `generated_at` + `model` header (mandatory — a tree
without a timestamp is not auditable), one inline provenance comment per node, and gray
zones as trailing comments. It imports nothing and makes zero LLM calls at inference.

## Complexity contract

The output must read like a tree a domain expert would hand-write. Tree depth/node count
should reflect domain complexity, not how many rounds the loop ran. If you wouldn't accept
the tree in a code review, it's over-engineered — let the `overengineering_critic` win that
round. Provenance lives in comments, never in logic.
