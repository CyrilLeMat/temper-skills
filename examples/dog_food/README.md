# Dog food checker — flagship example

> ⚠️ **Educational example, not veterinary advice.** Do not use the generated
> `dog_food_checker.py` to make real decisions about an animal's health.

Demonstrates the core promise: a `skill.md` that says only "consider known toxic
foods... when in doubt, say no" is distilled, via the adversarial loop, into a
deterministic `dog_food_checker.py` that surfaces edge cases the prompt never
contained — e.g. low-fat peanut butter → xylitol → acutely toxic.

```bash
export ANTHROPIC_API_KEY=...
python examples/dog_food/run.py          # scripted: runs to convergence, exports the tree
# or, interactively, with the per-round gate:
temper-skills ingest examples/dog_food/skill.md --profile standard --out examples/dog_food/dog_food_checker.py
```

Then verify zero-LLM inference:

```python
from examples.dog_food.dog_food_checker import can_dog_eat
can_dog_eat({"food_item": "peanut butter", "food_form": "low_fat", "dog_weight_kg": 10})
```
