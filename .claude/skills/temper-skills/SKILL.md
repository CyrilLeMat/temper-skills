---
name: temper-skills
description: Compile an agent's decision logic (a prompt or skill.md) into a deterministic, versionable Python decision tree via an adversarial multi-persona loop that runs natively in Claude Code — proposer plus persona subagents through the Task tool, entirely on your Claude Code subscription, no install and no API key. Use inside Claude Code when the user wants to "temper", "distill", "freeze", or "harden" the routing/decision logic of a skill, prompt, or playbook into testable code, or to turn a skill.md into a decision tree. Not for continuous scoring, text generation, or agents without a subagent primitive (there, use the temper-skills CLI/library instead).
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

Four attackers plus two structural counterweights: the `overengineering_critic` (every round)
and the `schema_critic` (standard & audit-grade). Spawn **one subagent per persona each round**,
in parallel (one message, multiple Task calls). Keep each subagent prompt **lean and
self-contained** — do not make them read this skill or the repo.

The two counterweights pull opposite ways and are both essential: the `overengineering_critic`
shrinks the tree *within* the schema; the `schema_critic` argues the *schema itself* is too thin
to be correct (e.g. on `decide_meal` it flags the missing `minutes_since_exercise` that forces
the tree to punt). Neither adds validation cases.

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
<!-- END GENERATED:personas -->

Each persona subagent returns ONLY this JSON:
```json
{"persona": "<name>", "score": 0-10, "verdict": "ok|missing_case|collapsible|contradiction|schema_too_thin",
 "detail": "<one sentence>", "proposed_case": "<concrete feature assignment it mishandles, or null>",
 "proposed_tests": [{"input": {<feature: value>}, "expected": "<best-guess outcome>", "rationale": "<one line>"}],
 "proposed_features": ["<name: type — why the source needs it>"]}
```

`proposed_tests` is how the validation set gets built (see below). **Every attacker persona
must add a case here whenever it finds a flaw** — a full feature assignment plus the outcome
it believes correct. Tell each subagent these are proposals a human will ratify, not ground
truth. The two counterweights always return `proposed_tests: []`:

- The `overengineering_critic` removes complexity; it adds no cases and no features.
- The `schema_critic` uses `verdict: "schema_too_thin"` and fills **`proposed_features`** — each
  a `name: type — why` for a feature the source implies but the schema can't express. Every
  other persona leaves `proposed_features` empty. These are **advisory and may re-open the
  schema gate** (see below), not branches you add to the tree.

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
| `standard` | 20 | 3 | on | on | `edge_case_hunter`, `domain_expert`, `schema_critic`, `overengineering_critic` |
| `audit-grade` | 50 | 5 | on | on | `literalist`, `edge_case_hunter`, `bad_faith_actor`, `domain_expert`, `schema_critic`, `overengineering_critic` |
<!-- END GENERATED:profiles -->

<!-- BEGIN GENERATED:convergence -->
_Generated from `temper_skills/distill.py` — edit there, then run `python -m temper_skills.skill_docs`._

The loop stops when **no round improves on the best for `stop after N quiet rounds` consecutive rounds** (a plateau — whether high, a good tree, or low, can't improve), or the round cap is hit, or the user stops. The per-profile `N` and cap are in the profile table above. Convergence is a *plateau*, not an absolute score threshold.
<!-- END GENERATED:convergence -->

## The loop

1. **Draft** the initial tree yourself (proposer) from the skill + schema + constraints.
   Cover obvious cases. Where the source **underdetermines** an answer (a genuine gray
   zone — e.g. "the skill says 'when in doubt, say no' but never lists safe foods"),
   **resolve it yourself with the safest defensible default** consistent with the HARD
   constraints and the source's stated bias, and **record it as a `gray_zone`** on the
   node. Do **not** stop to ask the user how to resolve it — see "Gray zones" below.
2. **Critique** — spawn the profile's panel (the attackers + the two counterweights) in
   parallel with the current tree; collect their scored JSON verdicts.
3. **Arbitrate** — spawn **one independent `arbiter` subagent**, separate from you-the-proposer.
   It receives the current tree, the panel's verdicts, the constraints, and the schema — but
   **not** your defense of the draft — and rules `kept` / `changed` / `rejected` per persona
   with a one-line rationale (the *arbitrage log*), then returns the revised tree. It owes the
   draft no deference: keep a branch only because the logic and source justify it, not because
   it is already there; add a branch only if a critique justifies it AND an expert would write
   it by hand; collapse branches the `overengineering_critic` flags; honor the `schema_critic`
   (see re-gate below); never contradict a HARD constraint. You then apply its tree and track
   `rounds_survived` per node (matched by condition). **Do not arbitrate your own draft** — the
   proposer defending its own tree is the bias this split removes. (For a `quick`/unattended run
   you may fold the arbiter back into the proposer to save a spawn; standard/audit-grade always
   use a separate arbiter.)
4. **Show the round panel** — round N, per-persona `score/10` (sorted worst-first), the
   arbitrage log, current tree preview, and `min/mean` score.
5. **Gate** — ask the user: Continue · Stop and review · Abort. (Skip the gate only if they
   asked for an unattended/quick run.)
6. **Converge** — apply the convergence rule from *Profiles & convergence* above (plateau on
   no improvement for the profile's quiet-round count, the round cap, or the user stops).

### Build the validation set as you go — written to disk every round

Pick one `run_id` for the whole temper (e.g. a UTC timestamp) and reuse it every round. Each
round, after you apply the arbiter's tree, harvest the `proposed_tests` from every persona
EXCEPT the `overengineering_critic` and **write them to disk immediately** by piping them to
the deterministic per-round writer — do not wait for export:

```bash
echo '<this round's proposed_tests as a JSON list>' | \
  python -m temper_skills.update_validation <fn>.tree.json output/<fn>.py \
    --round <N> --run-id <run_id>
```

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
- The **only** blocking interactions in the whole run are: (1) the one-time schema
  accept/edit, and (2) the per-round Continue / Stop / Abort gate. If you're about to ask
  the user anything else, stop — make the defensible call, record it, and surface it.

### Schema gaps: advisory, with one principled re-gate

The `schema_critic` reports features the source needs but the schema can't express (it can't
add a branch — the feature doesn't exist). Handle its findings like this:

- **Advisory by default.** Record each gap as a `gray_zone` on the node that had to punt or
  over-approximate (e.g. `decide_meal`'s "no minutes-since-exercise → route to wait"). The
  tree ships with the limitation documented, not hidden.
- **Re-gate only when load-bearing.** If a gap is so central that the tree can't be correct
  without it, you may **re-open the schema accept/edit gate once** (gate #1) to add the
  feature, then reseed the loop. This is the *single* sanctioned exception to "exactly two
  gates" — and it's still gate #1, surfaced from evidence, not a new kind of question. Don't
  reopen for a marginal nice-to-have; record those as gray zones and move on.

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
