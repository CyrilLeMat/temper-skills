# Dog food checker — flagship example

> ⚠️ **Educational example, not veterinary advice.** Do not use the generated
> `dog_food_checker.py` to make real decisions about an animal's health.

Demonstrates the core promise: a 4-line `skill.md` ("known toxic foods → no; when in
doubt, say no") is distilled, via the adversarial loop, into a deterministic decision
tree you can read, diff, and run with zero LLM calls.

## The checked-in artifact

`dog_food_checker.py` is the **actual output of a `/temper` subagent run** on the Claude
Code subscription (its provenance is captured in `dog_food_tree.json`). Notable: the loop
*inferred its own minimal schema* — branching on `food_item` only — and the
`overengineering_critic` **dropped** `dog_weight_kg`, `food_form`, and dose tables, because
a skill this thin doesn't justify them. It converged in 2 rounds (min score 2 → 8). The one
thing the source underdetermines — whether to ever answer "yes" with no ratified safe foods —
is recorded as the tree's lone **gray zone**, ratified by the human at the gate.

Regenerate it deterministically from its provenance any time:

```bash
python -m temper_skills.export_tree examples/dog_food/dog_food_tree.json examples/dog_food/dog_food_checker.py
```

## Producing your own

**On a Claude Code subscription (no API key)** — the subagent skill:

```
/temper examples/dog_food/skill.md
```

**As a library / CLI** (API key or agent CLI) — `run.py` uses an explicit, richer
`DogFoodQuery` schema, which yields a different (form/dose-aware) tree:

```bash
python examples/dog_food/run.py
# or: temper-skills ingest examples/dog_food/skill.md --backend auto --profile standard \
#       --out examples/dog_food/dog_food_checker.py
```

> The subscription run and the explicit-schema run produce **different, both-defensible**
> trees — that's expected (compile-time non-determinism; the tree is a reviewed, versioned
> artifact, not a guaranteed-reproducible output).

## Verify zero-LLM inference

```python
from examples.dog_food.dog_food_checker import can_dog_eat
can_dog_eat({"food_item": "chocolate"})        # 'no — toxic, never feed'
can_dog_eat({"food_item": "carrot"})           # 'yes — safe in moderation'
can_dog_eat({"food_item": "dark chocolate"})   # 'no — when in doubt …' (see boundary note below)
```

## Validate it (§4.5)

`validation_set.json` is a held-out labeled set; the shipped tree passes it 100%
(and `tests/test_validate.py` pins that in CI):

```bash
temper-skills validate examples/dog_food/dog_food_checker.py \
  examples/dog_food/validation_set.json --fn can_dog_eat
# Agreement: 21/21 (100.0%)
```

Add an un-ratified safe food (e.g. `{"food_item": "watermelon", "expected": "yes"}`) and the
harness surfaces it as a disagreement and exits non-zero — exactly the "the safe-list is
incomplete" signal §4.5 is for (a tree gap to fix, or a label to reconsider).

## The boundary the loop itself flagged

`can_dog_eat("dark chocolate")` returns "no" **only because the default is "no"** — the
exact-match toxin set doesn't contain the literal string `"dark chocolate"`. Two personas
(`literalist`, `bad_faith_actor`) independently flagged that the real exposure is the
**upstream normalization** of free text → a `food_item` keyword, which is *outside* the
tree's determinism guarantee. See the main README's "What it is not".
