# Dog food checker — flagship example

> ⚠️ **Educational example, not veterinary advice.** Do not use the generated code to make
> real decisions about an animal's health.

A 4-line skill ("known toxic foods → no; when in doubt, say no") compiled into a
deterministic decision tree via the adversarial loop. The folder is split so you can see
exactly what you **provide** vs. what the tool **generates**:

```
input/                     ← what you provide
  skill.md                 the prompt/skill to temper (the only required input)
  schema.py                optional: an explicit DogFoodQuery feature schema
  validation_set.json      optional: a held-out labeled set to check the tree against

output/                    ← what temper-skills generates
  dog_food_tree.json       the tree's provenance (regenerate the .py from this)
  dog_food_checker.py      the deterministic decision tree — zero LLM calls at inference
  skill.tempered.md        a new skill that DELEGATES the decision to the tree
```

`input → temper → output`. The decision logic moves from untestable prose (`input/skill.md`)
into a reviewable, versionable function (`output/dog_food_checker.py`), and the tempered
skill (`output/skill.tempered.md`) rewires the agent to *call* that function instead of
re-deciding every time.

## Produce the outputs

**On a Claude Code subscription (no API key)** — the subagent skill:

```bash
/temper examples/dog_food/input/skill.md
```

**As a library / CLI** (API key or agent CLI) — `run.py` uses the explicit `input/schema.py`:

```bash
python examples/dog_food/run.py        # writes output/dog_food_checker.generated.py
# or:
temper-skills ingest examples/dog_food/input/skill.md --backend auto --profile standard \
  --out examples/dog_food/output/dog_food_checker.py
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
  examples/dog_food/input/validation_set.json --fn can_dog_eat
# Agreement: 21/21 (100.0%)
```

`tests/test_validate.py` pins this in CI. Add an un-ratified safe food
(`{"food_item": "watermelon", "expected": "yes"}`) to `input/validation_set.json` and the
harness surfaces it as a disagreement and exits non-zero — the "safe-list is incomplete"
signal.

## The boundary the loop itself flagged

`can_dog_eat("dark chocolate")` returns "no" **only because the default is "no"** — the
exact-match toxin set doesn't contain the literal string `"dark chocolate"`. Turning free
text into a normalized `food_item` keyword is **upstream and out of scope** (see the main
README's "What it is not"); the `literalist` / `bad_faith_actor` personas flag it every run.
