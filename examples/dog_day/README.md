# Dog day — the multi-decision flow (decompose demo)

> Educational example, not veterinary advice.

The companion to [`../dog_food/`](../dog_food/): where dog_food is a single (weak-fit)
decision, **dog_day is a *flow*** — a daily dog-care assistant that makes three calls and
then writes the owner a note. It's the example for `decompose`: temper freezes *one*
decision at a time, so a skill that holds several must be split first.

Run `audit` on it and it doesn't say "temper" — it says **DECOMPOSE FIRST**, because the
three axes would only *average* three different decisions.

The output is a **spec-compliant [Agent Skill](https://agentskills.io/specification)** — a
`SKILL.md` + `scripts/` + `assets/` folder, so the tempered flow is a portable skill any
skills-compatible agent can load, not a loose pile of files:

```
input/
  skill.md                  the flow: walk? · feed? · vet? · then write a note
output/
  dog-day/                  ← the tempered flow, as an Agent Skill (name matches the dir)
    SKILL.md                orchestrator: chains the 3 trees + writes the note (imports from scripts/)
    scripts/                executable code (spec: self-contained — the trees import nothing)
      decide_walk.py        the frozen tree (one per decision), with inline provenance
      decide_meal.py        coupled: just_exercised/minutes_since_exercise/had_full_meal_today ← decide_walk/day
      decide_vet.py         severity × duration × age (Ottawa-style)
      test_decide_*.py      behavior-lock tests (always green); disputes stay in the dataset, never xfail
    assets/                 spec: "Data files … schemas" live here
      decide_*.schema.py    the per-decision input contract
      *.validation.jsonl    per-decision validation dataset the loop built (committed; review to ratify)
```

This is the only **complete** decompose chain in the examples — the three trees are real
(tempered live on the `standard` profile via the subagent-mode loop, `claude-code-subagents`),
and the orchestrator chains them. They carry inline provenance (gray zones + critic notes) and
a per-decision validation set; after the latest standard re-temper (which added `temperature_c`
to `decide_walk` and `minutes_since_exercise` + `had_full_meal_today` to `decide_meal` via the
schema gate), **two cells are still *contested*** (the panel's label disagrees with the tree)
and flagged for ratification. Harden further with `--profile audit-grade`.

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

The committed result: a **spec-compliant Agent Skill** (`output/dog-day/`) — three small
deterministic trees in `scripts/` + a thin orchestrator `SKILL.md` that chains them, feeding
`decide_walk`'s outcome into `decide_meal` as `just_exercised`, and writes the note. That's the
DMN-vs-BPMN split: the decision logic is frozen code, the orchestration and the prose stay with
the model — packaged as a portable skill.

## Honest scope

`input/skill.md` is the only authored artifact you *need*; the `output/` mini-schemas are
shown ratified (what `decompose --emit-schemas` proposes). The three trees here were tempered
live on the `standard` profile via the subagent-mode loop (proposer + persona subagents, no
API key) — gated, with inline provenance and a panel-built validation set per decision. That
set is *proposed*, not ground truth: the five contested cells need a human to rule on them
before they gate. The trees are a reviewed artifact, not a reproducible output — re-running
won't byte-match.
