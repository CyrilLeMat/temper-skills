# Curbside parking — the everyday example

> Educational example with invented city rules ("Riverside"). Don't use it to fight a real
> ticket.

The relatable on-ramp that's also a **genuine fit**. "Can I park here right now?" is something
everyone has gotten wrong — and unlike "can my dog eat that?" (a flat, unbounded lookup the
loop thrashes on, see [`../dog_food/`](../dog_food/)), the difficulty here lives in the
**interactions of a closed feature space**: zone × day × hour × holiday × permit. There's no
infinite item list to enumerate, so the loop converges — its job is the precedence and the
boundary hours, not cataloguing curbs.

```
input/
  skill.md                the posted rules: no-stopping, street cleaning, meters, permits, precedence
output/
  schema.py               ParkingQuery — zone_type, day, hour, is_public_holiday, has_resident_permit
  validation_set.json     20 ratified cases exercising the interactions + the holiday/permit edges
  can_i_park.py           the deterministic advisor — zero LLM at inference (after a live run)
  skill.tempered.md       a parking skill that calls the advisor (after a live run)
```

`input/` is just the skill (the prose). Everything else — the schema the loop is pinned to,
the validation set it's graded against, and the tree it emits — lives in `output/`. The tree
and tempered skill land after a live loop run; the schema and validation set are committed.

## Why it's a good fit (and dog_food isn't)

Run the fitness pre-flight on both and the contrast is the whole point:

```bash
temper-skills audit examples/parking/input/skill.md     # verdict: TEMPER
temper-skills audit examples/dog_food/input/skill.md     # verdict: SKIP (flat lookup, H4)
```

Parking scores high on **combinatorics** (the verdict turns on how zone, day, hour, holiday,
and permit interact) and the schema **closes** (enums + a bounded `hour` + two bools, low
normalization burden) — the two axes dog_food fails.

## Run it

```bash
# subscription, no key:
/temper examples/parking/input/skill.md

# library / CLI (pin the schema so the tree matches the validation set):
temper-skills ingest examples/parking/input/skill.md --backend auto --profile standard -y \
  --schema examples/parking/output/schema.py:ParkingQuery --fn can_i_park \
  --out examples/parking/output/can_i_park.py \
  --examples examples/parking/output/validation_set.json
```

## What the loop finds (and why it converges)

The prose states the rules plainly; the loop turns them into the explicit **interactions and
precedence** a flat reading misses:

- **A public holiday suspends street cleaning and the meter — but not a no-stopping zone.** A
  hydrant is still a hydrant on Christmas. (The two-way gotcha drivers get wrong.)
- **A resident's permit exempts you from the permit rule, not from street cleaning.** Tuesday
  at 11am you move your car regardless.
- **The cleaning window beats the meter and permit rules** when both apply — strict precedence,
  not first-match.
- **The boundary hours** are real branches: free at 6pm in a meter zone, free at 8pm in a permit
  zone, free before enforcement starts.

Because the features are closed sets, `domain_expert` runs out of genuinely-new cases and
`overengineering_critic` collapses redundant branches — so scores stabilize and the loop
converges, instead of oscillating on a forever-growing list.

## Verify (§4.5)

```bash
temper-skills validate examples/parking/output/can_i_park.py \
  examples/parking/output/validation_set.json --fn can_i_park --match exact
# Agreement: 20/20 (100.0%)
```

The 20 cases are hand-authored ground truth (the same draft → ratify → freeze contract as the
other examples). The committed `output/` and a CI pin land once the example has had a live
loop run.
