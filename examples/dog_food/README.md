# Dog food checker — flagship example

> ⚠️ **Educational example, not veterinary advice.** Do not use the generated code to make
> real decisions about an animal's health.

A 4-line skill ("known toxic foods → no; when in doubt, say no") compiled into a
deterministic decision tree via the adversarial loop. This is the **bootstrap-from-nothing**
example: the *only* thing you bring is the skill (`input/skill.md`) — the loop proposes the
schema and drafts the validation cases, and you ratify both. Everything temper touches lands
in `output/`:

```
input/                     ← what you bring  (just the prose)
  skill.md                 the prompt/skill to temper — the ONLY required input

output/dog-food/           ← the tempered skill, as a spec-compliant Agent Skill (agentskills.io)
  SKILL.md                 delegates the decision to the tree (imports from scripts/)
  scripts/
    can_dog_eat.py         the deterministic decision tree — zero LLM calls at inference
    test_can_dog_eat.py    behavior-lock (always green) + test_..._ratified.py (asserts blessed truth)
  assets/                  spec: "Data files … schemas" live here
    can_dog_eat.schema.py  the DogFoodQuery contract
    can_dog_eat.validation.jsonl  the ratified labeled set (status: ratified)
```

`input → temper → output`. The decision logic moves from untestable prose (`input/skill.md`)
into a reviewable, versionable function (`output/dog-food/scripts/can_dog_eat.py`), and the
tempered `SKILL.md` rewires the agent to *call* that function instead of re-deciding every
time. The schema and the ratified validation set (in `assets/`) are the contract
and the correctness gate — neither was hand-authored up front; both started as loop proposals
a human approved (the `"status": "ratified"` tag in the set is what records the sign-off, not
the folder it sits in).

## Produce the outputs

**On a Claude Code subscription (no API key)** — the subagent skill:

```bash
/temper examples/dog_food/input/skill.md
```

**As a library / CLI** (API key or agent CLI) — start from only the skill. `run.py` runs the
schema-less path (`schema=None`); the loop infers the contract and drafts test cases:

```bash
python examples/dog_food/run.py        # writes output/dog_food_checker.generated.py
```

To bootstrap explicitly — draft the contract, ratify it, then distill against it:

```bash
# 1. propose the schema from the prose, then STOP for review
temper-skills ingest examples/dog_food/input/skill.md --propose-schema
#    → writes schema.proposed.py; edit/ratify it (the committed output/schema.py is one such result)

# 2. distill against the ratified contract + the ratified set grown from earlier rounds
temper-skills ingest examples/dog_food/input/skill.md --backend auto --profile standard \
  --schema examples/dog_food/output/schema.py:DogFoodQuery --fn can_dog_eat \
  --out examples/dog_food/output/dog_food_checker.py \
  --examples examples/dog_food/output/validation_set.json
```

> The subscription run and the explicit-schema run produce **different, both-defensible**
> trees (compile-time non-determinism — the tree is a reviewed artifact, not a reproducible
> output).

Regenerate the committed `.py` deterministically from its provenance any time:

```bash
python -m temper_skills.export_tree \
  examples/dog_food/output/dog_food_tree.json examples/dog_food/output/dog_food_checker.py
```

## About the committed output

`output/dog_food_checker.py` branches on **`food_item`, `food_form`, `dog_weight_kg`, and
`quantity_grams`** — the `DogFoodQuery` features that carry signal — and surfaces the §11
edge cases the source prose never stated: low-fat peanut butter → xylitol, a dose-by-weight
guard, and a zero/missing-weight case that returns `unknown` rather than `yes`. Underdetermined
points are recorded as **gray zones** (the unratified safe-list, the concentrated-form rule,
the placeholder dose threshold).

`dog_breed` is in the schema but the tree doesn't branch on it — a tree needn't use every
field; the schema is the *ceiling* on what it may use, not a checklist. And a thinner run can
prune further: a low-effort subscription `/temper` on this same skill often collapses to
`food_item`-only, because a 4-line skill doesn't compel dose tables (compile-time
non-determinism — see the note above).

## Verify it (§4.5)

```bash
temper-skills validate examples/dog_food/output/dog_food_checker.py \
  examples/dog_food/output/validation_set.json --fn can_dog_eat
# Agreement: 21/21 (100.0%)
```

`tests/test_validate.py` pins this in CI. Add an un-ratified safe food
(`{"food_item": "watermelon", "expected": "yes"}`) to `output/validation_set.json` and the
harness surfaces it as a disagreement and exits non-zero — the "safe-list is incomplete"
signal.

## The boundary the loop itself flagged

`can_dog_eat("dark chocolate")` returns "no" **only because the default is "no"** — the
exact-match toxin set doesn't contain the literal string `"dark chocolate"`. Turning free
text into a normalized `food_item` keyword is **upstream and out of scope** (see the main
README's "What it is not"); the `literalist` / `bad_faith_actor` personas flag it every run.
