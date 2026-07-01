# OSS license compatibility — the "moat" demo

> ⚠️ Educational example, not legal advice.

The plan's flagship moat domain (§8): **fully public, low-stakes, genuinely hard
combinatorics.** The verdict depends on the *interaction* of license × linking ×
distribution — exactly the long tail of edge cases a competent person gets wrong by hand,
and where the adversarial loop earns its keep. Closed feature space → it converges.

```
input/
  skill.md                a license-advice prompt (permissive vs copyleft, distribution, linking)
output/license-compat/   ← the tempered skill, as a spec-compliant Agent Skill (agentskills.io)
  SKILL.md                an advice skill that calls the assessor
  scripts/
    assess_license.py     the deterministic assessor — zero LLM at inference
    test_assess_license.py  behavior-lock + test_assess_license_ratified.py (18 ratified cases)
  assets/
    assess_license.schema.py       LicenseQuery — project_license, dependency_license, linking, distributing, modified
    assess_license.validation.jsonl  the ratified labeled set (interaction matrix + a None distributing)
```

## Run it

```bash
# subscription, no key:
/temper examples/license_compat/input/skill.md

# library / CLI (audit-grade — the full persona panel for a higher-stakes domain):
temper-skills ingest examples/license_compat/input/skill.md --backend auto --profile audit-grade -y \
  --schema examples/license_compat/output/schema.py:LicenseQuery --fn assess_license \
  --out examples/license_compat/output/assess_license.py \
  --examples examples/license_compat/output/validation_set.json
```

## The non-obvious edges the loop surfaces

These are the interactions the source prose only gestures at — the kind a human misses:

- **Distribution gates everything**: GPL/AGPL obligations don't trigger for internal-only use.
- **Copyleft propagation is conditional**: GPL forces your project to GPL *only* when linked
  (not mere aggregation) *and* distributed *into a non-GPL project* — three features at once.
- **AGPL reaches network use** and even separate-process aggregation → `must_offer_source`.
- **LGPL static vs dynamic**: dynamic into proprietary is fine; static needs review.
- **Apache-2.0 + GPLv2 = incompatible** (the patent-clause conflict) — the classic gotcha.

Because licenses are a closed set, `domain_expert` doesn't have an infinite tail to chase and
`overengineering_critic` collapses the permissive licenses into one branch — so it converges
to ~8 nodes instead of oscillating.

## Verify (§4.5)

```bash
temper-skills validate examples/license_compat/output/assess_license.py \
  examples/license_compat/output/validation_set.json --fn assess_license --match exact
# Agreement: 18/18 (100.0%)
```

Pinned in CI by `tests/test_validate.py`.
