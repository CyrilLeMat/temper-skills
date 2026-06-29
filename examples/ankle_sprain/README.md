# Sprained ankle — RICE vs POLICE (the "oh merde" demo)

> ⚠️ **Educational example, NOT clinical advice.** A real injury needs a real clinician.
> Public-health domains carry liability risk — the plan (§5/§7) flags medical triage as
> caution-only and "qualify as educational" before any public use.

The most *visceral* demonstration of H2 (the LLM as a good-enough oracle): the source
`skill.md` gives the **outdated RICE** advice (Rest, Ice, Compress, Elevate — complete rest,
ice generously). The adversarial loop, mobilizing public medical literature, **knows better**
and corrects it to **POLICE / PEACE & LOVE** (2019) — *protected early loading, not rest;
ice only briefly because prolonged icing slows healing*. That's an edge even general
practitioners miss — exactly the "oh merde" moment.

```
input/
  skill.md                the OUTDATED RICE first-aid prompt
output/
  schema.py               AnkleInjury — Ottawa criteria + sprain grade + time + age
  validation_set.json     16 ratified cases across the Ottawa matrix + protocol phases
  ankle_tree.json         provenance (audit-grade)
  assess_ankle.py         the deterministic advisor — zero LLM at inference
  skill.tempered.md       a first-aid skill that calls the advisor (now POLICE, not RICE)
```

## Why it converges (and is a strong fit)

- **Real combinatorics, closed space**: the **Ottawa Ankle Rules** are 5 interacting criteria
  (malleolar pain × lateral/medial bone tenderness × weight-bearing) that rule a fracture
  in or out — genuine branching, not a flat list. Layered with sprain grade × time × age.
- **`domain_expert`** supplies the RICE→POLICE correction and the age caveat (Ottawa is
  validated ~18–55); **`overengineering_critic`** keeps it to ~7 nodes; both reconcile, so
  scores stabilize.

## The non-obvious edges

- **RICE is obsolete** → `police_acute` (PEACE: protect, elevate, *avoid* prolonged ice,
  compress, educate) / `police_subacute` (LOVE: load, optimism, vascularisation, exercise).
- **Ottawa rules a fracture OUT**: malleolar pain *without* bone tenderness and able to bear
  weight → not imaging, manage as a sprain (case 12).
- **Age boundary**: under 18 / over 55 → see a clinician (Ottawa less validated).
- **Deformity / can't-bear-weight** short-circuit to urgent care / clinician before protocol.

## Run it

```bash
# subscription, no key:
/temper examples/ankle_sprain/input/skill.md

# library / CLI (audit-grade for a higher-stakes domain):
temper-skills ingest examples/ankle_sprain/input/skill.md --backend auto --profile audit-grade -y \
  --schema examples/ankle_sprain/output/schema.py:AnkleInjury --fn assess_ankle \
  --out examples/ankle_sprain/output/assess_ankle.py \
  --examples examples/ankle_sprain/output/validation_set.json
```

## Verify (§4.5)

```bash
temper-skills validate examples/ankle_sprain/output/assess_ankle.py \
  examples/ankle_sprain/output/validation_set.json --fn assess_ankle --match exact
# Agreement: 16/16 (100.0%)
```

Pinned in CI by `tests/test_validate.py`.
