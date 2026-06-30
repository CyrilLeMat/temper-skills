# Dog day — the multi-decision flow (decompose demo)

> Educational example, not veterinary advice.

The companion to [`../dog_food/`](../dog_food/): where dog_food is a single (weak-fit)
decision, **dog_day is a *flow*** — a daily dog-care assistant that makes three calls and
then writes the owner a note. It's the example for `decompose`: temper freezes *one*
decision at a time, so a skill that holds several must be split first.

Run `audit` on it and it doesn't say "temper" — it says **DECOMPOSE FIRST**, because the
three axes would only *average* three different decisions.

```
input/
  skill.md                  the flow: walk? · feed? · vet? · then write a note
output/                     ← schemas proposed by `decompose --emit-schemas` + ratified; trees from a live run
  decide_walk.schema.py     DecideWalk  — hours-since × weather × energy × availability
  decide_meal.schema.py     DecideMeal  — coupled: just_exercised comes from decide_walk
  decide_vet.schema.py      DecideVet   — severity × duration × age (Ottawa-style)
  decide_walk.py            the frozen tree (one per decision), with inline provenance
  decide_meal.py
  decide_vet.py
  *.proposed_examples.json  per-decision validation cases the loop built (gitignored; review to ratify)
  dog_day.tempered.md       the orchestrator: chains the 3 trees + writes the note
```

This is the only **complete** decompose chain in the examples — the three trees are real
(tempered live on the `standard` profile via the subagent-mode loop, `claude-code-subagents`),
and the orchestrator chains them. They carry inline provenance (gray zones + critic notes) and
a per-decision validation set; five cells are still *contested* (the panel's label disagrees
with the tree) and flagged for ratification. Harden further with `--profile audit-grade`.

## The decisions the flow holds

| Decision | What it decides | Coupling | Likely audit |
|---|---|---|---|
| `decide_walk` | walk now / short / postpone / skip | independent | **temper** |
| `decide_meal` | full / light / treat / none | **consumes `decide_walk`** (walked → exercised) | **temper** |
| `decide_vet` | urgent / soon / monitor / fine | independent | **temper** |
| *generative* | write the owner's note | — | left to the model |

`decide_meal` is the coupling demo: its `just_exercised` feature is fed by `decide_walk`'s
outcome. The orchestrator chains the two trees — the trees themselves stay pure functions.

## The workflow

```bash
# 1. the audit flags it as a flow, not one decision
temper-skills audit examples/dog_day/input/skill.md          # → DECOMPOSE FIRST (~3 decisions)

# 2. split it, and draft a mini-schema per decision
temper-skills decompose examples/dog_day/input/skill.md --emit-schemas --out-dir examples/dog_day/output
#    prints the plan (3 decisions + 1 generative, with coupling) and writes decide_*.schema.py

# 3. ratify each schema, then temper each decision into its own tree
temper-skills ingest examples/dog_day/input/skill.md --backend auto -y \
  --schema examples/dog_day/output/decide_walk.schema.py:DecideWalk --fn decide_walk \
  --out examples/dog_day/output/decide_walk.py
#    … repeat for decide_meal and decide_vet
```

The committed result: **three small deterministic trees + a thin orchestrator skill**
(`dog_day.tempered.md`) that chains them — feeding `decide_walk`'s outcome into `decide_meal`
as `just_exercised` — and writes the note. That's the DMN-vs-BPMN split: the decision logic
is frozen code, the orchestration and the prose stay with the model.

## Honest scope

`input/skill.md` is the only authored artifact you *need*; the `output/` mini-schemas are
shown ratified (what `decompose --emit-schemas` proposes). The three trees here were tempered
live on the `standard` profile via the subagent-mode loop (proposer + persona subagents, no
API key) — gated, with inline provenance and a panel-built validation set per decision. That
set is *proposed*, not ground truth: the five contested cells need a human to rule on them
before they gate. The trees are a reviewed artifact, not a reproducible output — re-running
won't byte-match.
