---
name: dog-day
description: "Tempered orchestrator: chains frozen, deterministic decision trees (decide_walk, decide_meal, decide_vet) and keeps only the generative note. Use to run a daily dog-care flow with each decision made by code (no LLM) and only the prose left to the model."
---

# Dog day — daily dog-care assistant (tempered orchestrator)

> Educational example, not veterinary advice.

You run the day with the owner's dog. **The three decisions below are frozen** — extract the
features, call the tree, relay the verdict, don't re-decide. Only the final note is yours to
phrase. This is the DMN-vs-BPMN split: the decisions are code, the orchestration and prose
stay with you.

## 1. Walk? — frozen, `decide_walk`
Extract `hours_since_last_walk` (float), `weather` (`clear|rain|storm|heat|snow|cold`),
`temperature_c` (float or `None`), `dog_energy` (`low|normal|high`), `owner_available` (bool),
`is_late` (bool). Give `temperature_c` when you know it — the `>30°C` heat rule branches on the
measured value; the `heat` label is only a fallback when temperature is unknown.
```python
from decide_walk import decide_walk
walk = decide_walk({"hours_since_last_walk": ..., "weather": ..., "temperature_c": ...,
                    "dog_energy": ..., "owner_available": ..., "is_late": ...})
```

## 2. Meal? — frozen, `decide_meal` (chained from the walk)
The walk feeds the meal — that's the coupling. Pass both whether the dog exercised **and how
long ago**, plus whether it has already had a full meal earlier today:
```python
from decide_meal import decide_meal
just_exercised = walk in ("walk_now", "normal_walk")
meal = decide_meal({"hours_since_last_meal": ..., "time_of_day": ...,
                    "last_meal_size": ..., "just_exercised": just_exercised,
                    "minutes_since_exercise": ...,   # minutes since that walk, or None
                    "had_full_meal_today": ...})     # whole-day flag, or None
```

## 3. Vet? — frozen, `decide_vet` (independent)
Extract `symptom`, `severity` (`mild|moderate|severe`), `duration_hours`, `age_years`.
```python
from decide_vet import decide_vet
vet = decide_vet({"symptom": ..., "severity": ..., "duration_hours": ..., "age_years": ...})
```

## 4. The note — generation, yours
Write the owner a short, warm summary covering the walk call, the meal plan, any vet guidance,
and anything to watch. This step is **not** frozen — phrase it naturally.

## Gray zones to surface (recorded by the temper loop — provenance lives in each `decide_*.py`)
- `decide_walk`: **measured `temperature_c` overrides the `heat` label** — `>30°C` always skips
  to a toilet break; the `heat` label only skips when temperature is unknown (`None`). In
  storm/heat the dog gets the toilet break even if the owner is away or the walk is overdue.
  **snow/cold have no branch** (the source sets no cold threshold) — they walk as normal.
- `decide_meal`: the **30-minute rule is now measured** via `minutes_since_exercise` — within
  30 min (or unknown timing) the dog rests first (`wait_then_full_meal`); rested ≥30 min and not
  yet full today → a full meal. The **evening skip** uses the whole-day `had_full_meal_today`
  (falling back to `last_meal_size=='full'` when unknown) and caps an already-fed dog to a treat,
  even after an evening walk. A dog that **ate nothing today** gets a full meal, not a treat.
- `decide_vet` thresholds (severe / >48h / puppy-or-senior) are educational, not clinical —
  when unsure, say "call the vet." Outcomes rank `vet_urgent > vet_soon > vet_call > monitor_home`.

## Cases awaiting your ratification
Each tree ships a `<decision>.validation.jsonl` the loop built from the panel's findings
(proposals, **not** ground truth — they don't gate anything until you ratify). The committed
behavior-lock tests stay green (they assert the
tree's own output), and disagreements live in the dataset as data (`"agrees": false`), never as
failing or `xfail` tests. After this re-temper, **two cells are contested** — the panel's label
disagrees with what the tree returns. Both are the same precedence call, the highest-value one to
rule on:
- `decide_meal`: **evening + already-full-today + just exercised + within 30 min** → the tree
  returns `treat_only` (the "a treat at most" cap wins); `edge_case_hunter` proposed
  `wait_then_full_meal` (arguing a treat is still food inside the 30-min window). The arbiter
  rejected the swap because promising a full meal would re-break the evening cap. The four-outcome
  set can't express "wait, then a treat" — resolving this may mean adding that outcome.
