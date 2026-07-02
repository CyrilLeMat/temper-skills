---
name: temper-skills
description: Give an agent skill's decision logic a test suite and a deterministic implementation — a labeled validation dataset plus versionable Python — via an adversarial multi-persona loop that runs natively in Claude Code: proposer plus persona subagents through the Task tool, entirely on your Claude Code subscription, no install and no API key. Use inside Claude Code when the user wants to "test", "eval", "audit", "temper", "distill", "freeze", or "harden" the routing/decision logic of a skill, prompt, or playbook ("test my skill", "what is this skill deciding?"), to audit a whole skills directory, or to turn a skill.md into a decision tree. Not for continuous scoring, text generation, or agents without a subagent primitive (there, use the temper-skills CLI/library instead).
license: Apache-2.0
allowed-tools: Task, Bash, Read, Write
metadata:
  author: hellosunrise
  version: "0.1.0"
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

**You make the decisions; the loop is the point.** The schema and the tree **co-evolve** — you
start from a *naive* schema + a naive tree and let the loop grow and prune both. There are
**exactly two** human touchpoints, and no others:

1. **The per-round gate** — Continue / Stop / Abort (skipped on `quick`). The only mid-run block.
2. **The final review** — before shipping, the user reviews the *co-evolved* schema, the outcome
   set, the recorded gray zones, and the validation dataset. This is review-the-output (a
   sign-off), **not** answering questions mid-run.

There is **no up-front schema gate**. Seed a naive schema yourself and start the loop; the
`schema_critic` grows it, the `outcome_critic` flags a too-coarse outcome set, and the
`overengineering_critic` + the earn-a-branch guard prune what doesn't earn its place. The schema
is a *loop output*, reviewed at the end (it's the caller's integration contract), not a
pre-commitment.

For **everything else, decide and record — do not ask.** Specifically, **never** raise an
`AskUserQuestion` / multiple-choice modal to have the user choose feature breadth, whether to
keep/drop a branch or feature, how to resolve a gray zone, or any "which design do you prefer"
question. Those are the loop's job: the critics grow/prune, and you resolve gray zones with the
safest defensible default and **record** them (see Gray zones). If you catch yourself about to
open a question modal for anything other than the per-round gate: stop, make the defensible call,
record it, and keep going.

## Inputs

- A target `skill.md` / prompt (the logic to migrate), path given by the user.
  **If the path is a directory** (a skill library), do not start the loop: audit each
  discovered skill yourself — one judged pass per skill (decisiveness / combinatorics /
  stakes, plus how many features pin to a bounded value space) — and present a ranked
  findings table (skill · verdict · top finding · fix), most actionable first. The audit
  is a report worth having on its own; offer to temper the top pick, don't assume it.
- A **schema**: the pre-computed structured features the tree may branch on. If the user
  doesn't supply one, infer it from the skill (feature name + type + one-line meaning).
- Optional `hard` constraints (non-negotiable rules) and a few ratified examples.

Branch only on schema features. Conditions are valid Python boolean expressions over the
feature names (e.g. `food_item == "chocolate"`) and must be **None-safe** — any feature may
be absent at inference, so guard before comparing (`x is not None and x < 1`, never bare
`x < 1`) and coerce strings (`(s or "").strip().lower()`). A condition must never raise on a
missing feature.

### Seed a naive schema — the loop co-evolves it

Do **not** try to get the schema right up front, and do **not** gate on it. Seed a *naive,
tight* schema — the features the source obviously decides on — and start the loop. Drop features
that are circular (a feature that *is* the answer, like `is_known_toxic_food`); when in doubt
leave a plausible feature out. Then let the loop co-evolve it:

- the **`schema_critic`** grows it — each round it can name a feature the source implies that the
  current schema can't express (e.g. `minutes_since_exercise` on `decide_meal`). You **add** it
  to the working schema so the very next round can branch on it.
- the **earn-a-branch guard** prunes it — a feature you added must earn a surviving branch within
  ~2 rounds (the proposer actually branches on it and it survives the `overengineering_critic`).
  If it never does, **revert it** out of the schema and record it as an advisory gap. This bounds
  schema size by tree size, so the loop still converges — the schema is no longer a fixed ceiling.
- the **`overengineering_critic`** prunes branches within the schema, every round.

The user does not choose feature breadth — that is exactly what the co-evolution is for.
Offloading it to the user defeats the tool. The user's only schema involvement is the **final
review** (below): they read the co-evolved schema + outcome set and sign off, because it's the
contract the caller must extract against.

So the human touchpoints are exactly two: (1) the per-round Continue / Stop / Abort gate, and
(2) the final review/sign-off. Nothing else is a question for them.

## The personas

Four attackers plus three structural counterweights: the `overengineering_critic` (every round)
and the two expressiveness critics — `schema_critic` and `outcome_critic` (both standard &
audit-grade). Spawn **one subagent per persona each round**, in parallel (one message, multiple
Task calls). Keep each subagent prompt **lean and self-contained** — do not make them read this
skill or the repo.

The counterweights pull in three directions and are all essential; none adds validation cases:
- the `overengineering_critic` shrinks the tree *within* the current schema and outcome set;
- the `schema_critic` argues the *input side* is too thin — a feature the source implies but the
  schema can't express (e.g. on `decide_meal`, the missing `minutes_since_exercise` that forces
  the tree to punt);
- the `outcome_critic` argues the *output side* is too coarse — an answer the source implies but
  the outcome vocabulary can't express, so two distinct correct answers collapse into one label
  (e.g. on `decide_meal`, no way to say "wait, then a treat" — only `wait_then_full_meal` or
  `treat_only`). It's the exact dual of the `schema_critic`: challenge outputs, not just inputs.

<!-- BEGIN GENERATED:personas -->
_Generated from `temper_skills/sources.py` — edit there, then run `python -m temper_skills.skill_docs`._

| persona | always-on | angle (the `style` the model is given) |
|---|---|---|
| `literalist` | — | exploits literal ambiguities in the schema |
| `edge_case_hunter` | — | seeks rare combinations of feature values |
| `bad_faith_actor` | — | tries to strategically circumvent the rule |
| `domain_expert` | — | tests with rare but plausible domain cases |
| `overengineering_critic` | ✅ every round | challenges every node: is this branch actually necessary, or is it loop richness rather than domain complexity? |
| `schema_critic` | ✅ standard & audit-grade | argues the schema is too thin — names a feature the source implies that the schema cannot express, instead of adding test cases |
| `outcome_critic` | ✅ standard & audit-grade | argues the outcome set is too coarse — names an outcome the source implies that the vocabulary cannot express (so two distinct answers collapse into one), instead of adding test cases |
<!-- END GENERATED:personas -->

Each persona subagent returns ONLY this JSON:
```json
{"persona": "<name>", "score": 0-10,
 "verdict": "ok|missing_case|collapsible|contradiction|schema_too_thin|outcome_too_coarse",
 "detail": "<one sentence>", "proposed_case": "<concrete feature assignment it mishandles, or null>",
 "proposed_tests": [{"input": {<feature: value>}, "expected": "<best-guess outcome>", "rationale": "<one line>"}],
 "proposed_features": ["<name: type — why the source needs it>"],
 "proposed_outcomes": ["<outcome — why (which two cases collapse today)>"]}
```

`proposed_tests` is how the validation set gets built (see below). **Every attacker persona
must add a case here whenever it finds a flaw** — a full feature assignment plus the outcome
it believes correct. Tell each subagent these are proposals a human will ratify, not ground
truth. The three counterweights always return `proposed_tests: []`:

- The `overengineering_critic` removes complexity; it adds no cases, features, or outcomes.
- The `schema_critic` uses `verdict: "schema_too_thin"` and fills **`proposed_features`** — each
  a `name: type — why` for a feature the source implies but the schema can't express. You **add**
  load-bearing ones to the working schema (co-evolution, see below); the earn-a-branch guard
  reverts any that don't get used. They are growth signals, not branches you add to the tree.
- The `outcome_critic` uses `verdict: "outcome_too_coarse"` and fills **`proposed_outcomes`** —
  each an `outcome — why` for an answer the source implies but the outcome set can't express.
  Widen the outcome set when the gap is load-bearing; otherwise record it as a gray zone (the
  output-side dual). Every other persona leaves both `proposed_features` and `proposed_outcomes`
  empty.

**`score` is always the TREE's robustness from your angle — 0 = the tree fails badly
through your lens, 10 = solid, nothing to add.** It is NOT how successful your attack
was: a persona that finds no weakness scores the tree *high* (≈9–10) and returns
`verdict: "ok"`, `proposed_case: null`. Tell every persona subagent this explicitly so
the scale is uniform across the panel.

## Profiles & convergence

The profile sets the round budget, the panel, and how convergence is measured. These values
are owned by `temper_skills/distill.py` — do not hand-edit the table:

<!-- BEGIN GENERATED:profiles -->
_Generated from `temper_skills/distill.py` — edit there, then run `python -m temper_skills.skill_docs`._

| profile | max rounds | stop after N quiet rounds | per-round gate | provenance comments | adversary panel |
|---|---|---|---|---|---|
| `quick` | 8 | 2 | off | off | `edge_case_hunter`, `overengineering_critic` |
| `standard` | 20 | 3 | on | on | `edge_case_hunter`, `domain_expert`, `schema_critic`, `outcome_critic`, `overengineering_critic` |
| `audit-grade` | 50 | 5 | on | on | `literalist`, `edge_case_hunter`, `bad_faith_actor`, `domain_expert`, `schema_critic`, `outcome_critic`, `overengineering_critic` |
<!-- END GENERATED:profiles -->

<!-- BEGIN GENERATED:convergence -->
_Generated from `temper_skills/distill.py` — edit there, then run `python -m temper_skills.skill_docs`._

The loop stops when **no round improves on the best for `stop after N quiet rounds` consecutive rounds** (a plateau — whether high, a good tree, or low, can't improve), or the round cap is hit, or the user stops. The per-profile `N` and cap are in the profile table above. Convergence is a *plateau*, not an absolute score threshold.
<!-- END GENERATED:convergence -->

## The loop

1. **Draft** a naive initial tree yourself (proposer) from the skill + naive schema +
   constraints. Cover obvious cases. Where the source **underdetermines** an answer (a genuine
   gray zone — e.g. "the skill says 'when in doubt, say no' but never lists safe foods"),
   **resolve it yourself with the safest defensible default** consistent with the HARD
   constraints and the source's stated bias, and **record it as a `gray_zone`** on the
   node. Do **not** stop to ask the user how to resolve it — see "Gray zones" below.
2. **Critique** — spawn the profile's panel (the attackers + the structural counterweights) in
   parallel with the current tree; collect their scored JSON verdicts.
3. **Co-evolve the schema/outcomes** — apply the expressiveness critics *before* arbitrating so
   the same round can use them:
   - if the `schema_critic` named a feature (`proposed_features`), **add it to the working
     schema** and note the round you added it. Now the arbiter can branch on it.
   - if the `outcome_critic` named an outcome (`proposed_outcomes`), **widen the outcome set** if
     the gap is load-bearing (else record it as a gray zone).
   - **earn-a-branch-or-revert:** a feature/outcome you added must earn a surviving branch within
     ~2 rounds. If, ~2 rounds after you added it, no branch uses it (or the
     `overengineering_critic` would cut it), **revert it** and record it as an advisory gap. This
     keeps the schema no bigger than the tree needs.
4. **Arbitrate** — spawn **one independent `arbiter` subagent**, separate from you-the-proposer.
   It receives the current tree, the panel's verdicts, the constraints, and the **current
   (possibly grown) schema** — but **not** your defense of the draft — and rules `kept` /
   `changed` / `rejected` per persona with a one-line rationale (the *arbitrage log*), then
   returns the revised tree. It owes the draft no deference: keep a branch only because the logic
   and source justify it, not because it is already there; add a branch only if a critique
   justifies it AND an expert would write it by hand (including branching on a newly-added
   feature); collapse branches the `overengineering_critic` flags; never contradict a HARD
   constraint. You then apply its tree and track `rounds_survived` per node (matched by
   condition). **Do not arbitrate your own draft** — the proposer defending its own tree is the
   bias this split removes. (For a `quick`/unattended run you may fold the arbiter back into the
   proposer to save a spawn; standard/audit-grade always use a separate arbiter.)
5. **Write the validation dataset** — pipe this round's `proposed_tests` to the per-round writer
   (see below) so `output/<fn>.validation.jsonl` and its behavior-lock test grow on disk.
6. **Show the round panel** — round N, per-persona `score/10` (sorted worst-first), the
   arbitrage log, any schema/outcome change this round, current tree preview, and `min/mean`.
7. **Gate** — ask the user: Continue · Stop and review · Abort. (Skip the gate only if they
   asked for an unattended/quick run.)
8. **Converge** — apply the convergence rule from *Profiles & convergence* above (plateau on
   no improvement for the profile's quiet-round count, the round cap, or the user stops). A
   schema/outcome change is an improvement — it resets the quiet-round count.

### Loop invariants

<!-- BEGIN GENERATED:loop-invariants -->
_Generated from `temper_skills/distill.py / validation_case.py` — edit there, then run `python -m temper_skills.skill_docs`._

- **earn-a-branch window:** an added feature/outcome must earn a surviving branch within **2 rounds** or be reverted to an advisory gap.
- **case harvest excludes:** `overengineering_critic`, `schema_critic`, `outcome_critic` — the structural critics restructure; they don't add cases.
- **case statuses:** `proposed` → `resolved` → `ratified` — only a human-set `ratified` gates anything.
- **the only mid-run gate:** Continue · Stop and review · Abort. Everything else is decided, recorded, and reviewed at the end.
<!-- END GENERATED:loop-invariants -->

### Build the validation set as you go — written to disk every round

Pick one `run_id` for the whole temper (e.g. a UTC timestamp) and reuse it every round. Each
round, after you apply the arbiter's tree, harvest the `proposed_tests` from every persona
EXCEPT the structural critics — `overengineering_critic`, `schema_critic`, `outcome_critic`
(they restructure; they don't add cases) — and **write them to disk immediately** by piping
them to the deterministic per-round writer — do not wait for export:

```bash
echo '<this round's proposed_tests as a JSON list>' | \
  python scripts/update_validation.py <fn>.tree.json output/<fn>.py \
    --round <N> --run-id <run_id>
```

(`scripts/` here is this skill's own vendored, stdlib-only copy — no install needed. The path
is relative to the skill directory; use the absolute path to `.../temper-skills/scripts/` if
your working directory is elsewhere.)

This is not optional and not deferred: the committed `output/<fn>.validation.jsonl` and the
behavior-lock test beside it must grow **every round**, so the user can watch the evidence
accrue. The writer is deterministic (no LLM) and does the bookkeeping for you:

- **dedups by input** (the first round to find a case owns its label/status; a later duplicate
  only appends its `source`), so the same case found twice counts once;
- **stamps `first_seen_round` + `run_id`** on each new case — the audit trail that answers "was
  this generated *this* session?";
- **refreshes every row's `tree_prediction` / `agrees` against the current tree** — so when a
  round changes the tree, prior cases re-evaluate automatically. Run it even on a *quiet* round
  (pipe `[]`) so a tree change still refreshes the dataset.

Each `proposed_test` is a `{input, expected, rationale, source: "<persona>#r<N>"}` object.
Because you keep one `<fn>.tree.json` per decision on disk and re-export it each round (see the
loop), the writer always scores against the round's live tree.

These are **proposals, not ground truth.** You are extending the validation set, not grading
your own work: never treat a panel-authored label as a ratified anchor, and never let it gate
anything. A disagreement (`"agrees": false`) is **data to review, never a failing test** — the
behavior-lock test only asserts what the tree returns, and the ratified test (emitted only once
a human blesses a label) is the only test allowed to fail. At review the user ratifies: they fix
any wrong label and set `"status": "ratified"` — only then does it gate CI and anchor that cell
on a re-run. Do **not** ask the user to ratify mid-run; it's a review-the-output step, like gray
zones.

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
- The **only** blocking interaction in the whole run is the per-round Continue / Stop / Abort
  gate. If you're about to ask the user anything else, stop — make the defensible call, record
  it, and surface it at the final review.

### Expressiveness gaps drive co-evolution (not a re-gate)

The `schema_critic` reports features the source needs but the schema can't express; the
`outcome_critic` reports answers the source needs but the outcome set can't express. In the
co-evolving model these are **not** a special "re-gate" — they are the normal growth signal:

- **Grow, don't just record.** When a critic names a load-bearing gap, **add** the feature to the
  working schema (or widen the outcome set) the same round, so the arbiter can branch on it next.
  You do not stop to ask the user — adding it is the loop's job.
- **Earn-a-branch-or-revert bounds the growth.** An added feature/outcome that never earns a
  surviving branch within ~2 rounds is **reverted** and recorded as an advisory gap (a
  `gray_zone` on the node that had to punt — e.g. an *outcome* gap "can't say 'wait, then a
  treat', so an already-fed dog that just exercised routes to `treat_only`"). This is what keeps
  a mutable schema from ballooning — a feature only survives if the tree actually uses it.
- **The user sees it at the final review.** The co-evolved schema, the outcome set, what grew,
  and what reverted are all surfaced for sign-off at the end — never as a mid-run question.

## Export (deterministic — no LLM): emit a spec-compliant Agent Skill dir

When the loop ends, emit the tempered result as a **spec-compliant Agent Skill folder**
(agentskills.io: `SKILL.md` + `scripts/` + `assets/`) with the vendored, stdlib-only
`skill_render.py` — no install. Write one `<fn>.tree.json` per decision, then a `spec.json`:

```json
{"name": "route", "description": "...", "original_skill": "<path to original skill.md>",
 "generative_steps": ["<any step you left generative>"],
 "decisions": [{"tree": "route.tree.json", "module": "route",
                "schema": "route.schema.py", "consumes": []}]}
```

```bash
python scripts/skill_render.py spec.json output/route/
```

That writes the whole skill: `output/route/SKILL.md` (delegates each decision to its tree —
extract features → call `from scripts.<module> import <fn>` → relay the verdict, never
re-derive), `scripts/<module>.py` (the frozen tree, self-contained) + its behavior-lock and
ratified tests, and `assets/` (the schema + the `.validation.jsonl` dataset). One decision →
a tempered skill; several → an orchestrator that chains them. It reconciles any existing
`.validation.jsonl` and folds in the tree's `proposed_examples`, so the per-round dataset
provenance (`first_seen_round`/`run_id`) is preserved.

(If you only want the raw tree + dataset, `python scripts/export_tree.py tree.json route.py`
still does just that. The `temper-skills` package, when installed, offers the same via
`python -m temper_skills.export_skill`, plus an LLM-*woven* variant that rewrites the original
prose in its own voice.)

Show the user what changed: the original skill re-decided every call; the tempered skill
extracts features, calls the tree, and relays the verdict — decision frozen, model still does
NL extraction + phrasing (§2.5).

`export_tree` reconciles the committed `route.validation.jsonl` the per-round writer already
built: it folds in any `proposed_examples` still in `tree.json`, refreshes every row's
prediction against the final tree (**without clobbering the `first_seen_round`/`run_id`
provenance**), and regenerates `test_route.py` (behavior lock — always green) plus
`test_route_ratified.py` (only if a case is ratified — the sole test allowed to fail). Show the
user the validation dataset as **cases awaiting ratification**, flagging every `"agrees": false`
row — those are the highest-value disagreements to rule on. Debates live in the dataset as data,
never as `xfail` tests.

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
per case; the exporter adds the tree's prediction and `"status": "proposed"`. In the normal
loop you won't populate it: the per-round writer already accumulated the cases into
`route.validation.jsonl`, and export reconciles that file. Use `proposed_examples` only for a
one-shot export with no prior per-round dataset. Omit it if ratified examples already pin every
contested cell.

The exported `route.py` carries a `generated_at` + `model` header (mandatory — a tree
without a timestamp is not auditable), one inline provenance comment per node, and gray
zones as trailing comments. It imports nothing and makes zero LLM calls at inference.

## Complexity contract

The output must read like a tree a domain expert would hand-write. Tree depth/node count
should reflect domain complexity, not how many rounds the loop ran. If you wouldn't accept
the tree in a code review, it's over-engineered — let the `overengineering_critic` win that
round. Provenance lives in comments, never in logic.
