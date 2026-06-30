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
Extract `hours_since_last_walk` (float), `weather` (`clear|rain|storm|heat`), `dog_energy`
(`low|normal|high`), `owner_available` (bool), `is_late` (bool).
```python
from decide_walk import decide_walk
walk = decide_walk({"hours_since_last_walk": ..., "weather": ..., "dog_energy": ...,
                    "owner_available": ..., "is_late": ...})
```

## 2. Meal? — frozen, `decide_meal` (chained from the walk)
The walk feeds the meal — that's the coupling:
```python
from decide_meal import decide_meal
just_exercised = walk in ("walk_now", "normal_walk")
meal = decide_meal({"hours_since_last_meal": ..., "time_of_day": ...,
                    "last_meal_size": ..., "just_exercised": just_exercised})
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
- `decide_walk`: in **storm/heat** the dog gets a short toilet break even if the owner is
  away or the walk is overdue — a toilet need can't be postponed. And **late + owner-away**
  falls through to a walk (the source says "don't postpone when late" but not who walks).
- `decide_meal`: **no minutes-since-exercise** feature exists, so any post-walk case routes to
  `wait_then_full_meal` — tell the owner to wait ~30 minutes. The **evening skip** wins even
  when the dog is overdue; a dog that **ate nothing today** gets a full meal, not a treat.
- `decide_vet` thresholds (severe / >48h / puppy-or-senior) are educational, not clinical —
  when unsure, say "call the vet." Outcomes rank `vet_urgent > vet_soon > vet_call > monitor_home`.

## Cases awaiting your ratification
Each tree ships a `*.proposed_examples.json` the loop built from the panel's findings
(proposals, **not** ground truth — they don't gate anything until you ratify). Five cells are
**contested** — the panel's label disagrees with what the tree returns; these are the
highest-value decisions to rule on:
- `decide_walk`: storm/heat + owner-away → tree says `toilet_break_only`, a reviewer proposed `postpone_walk` (×2).
- `decide_meal`: last meal *light* & recent → tree says `light_meal`, a reviewer proposed `full_meal`.
- `decide_vet`: puppy/senior + moderate + >48h → tree says `vet_soon`, a reviewer proposed `vet_call` (×2).
