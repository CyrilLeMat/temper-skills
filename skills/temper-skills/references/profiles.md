# Temper profiles

The `--profile` flag controls how hard the adversarial loop runs: how many rounds it
may take, how strict convergence is, which persona panel attacks the tree, and whether
provenance comments are written. Recommend one to the user from the table below.

> Source of truth: `temper_skills/distill.py` (`PROFILES` + `PROFILE_PERSONAS`). The table
> below is generated — do not hand-edit it; change the code and run
> `python -m temper_skills.skill_docs`.

<!-- BEGIN GENERATED:profiles -->
_Generated from `temper_skills/distill.py` — edit there, then run `python -m temper_skills.skill_docs`._

| profile | max rounds | stop after N quiet rounds | per-round gate | provenance comments | adversary panel |
|---|---|---|---|---|---|
| `quick` | 8 | 2 | off | off | `edge_case_hunter`, `overengineering_critic` |
| `standard` | 20 | 3 | on | on | `edge_case_hunter`, `domain_expert`, `schema_critic`, `outcome_critic`, `overengineering_critic` |
| `audit-grade` | 50 | 5 | on | on | `literalist`, `edge_case_hunter`, `bad_faith_actor`, `domain_expert`, `schema_critic`, `outcome_critic`, `overengineering_critic` |
<!-- END GENERATED:profiles -->

The **`overengineering_critic` is always on**, appended to every panel — it prunes branches
a thin skill doesn't justify, so the tree reads like one a domain expert would hand-write.

## How to choose

- **`quick`** — a fast tour or a throwaway demo. Fewest rounds, leanest panel, **no provenance
  comments**. The schema is still ratified (the gate is never skipped); `quick` drops the
  inline provenance, not the gate.
- **`standard`** (default) — the normal choice for a tree you'll keep. Diverse two-attacker
  panel, provenance comments, convergence at 3 quiet rounds.
- **`audit-grade`** — high-stakes, repeated, or audited decisions. Full four-attacker panel,
  stricter convergence (5 quiet rounds), up to ~50 rounds. More LLM calls, longer run.

## Cost

Cost scales with `rounds × (panel size + 1 proposer call)`. On the subscription backend
(`claude`/`opencode` CLI) there is **no metered cost** — the CLI prints
`subscription — no metered cost`. On the API backend (`ANTHROPIC_API_KEY`) each run reports
an estimated `~$` figure from LiteLLM; `audit-grade` costs the most because it runs the most
rounds against the largest panel.

## Not yet built (roadmap)

The deeper `audit-grade` behaviors described in the product design — tournament orchestration
across panels, required citations on each persona verdict, and per-gray-zone human sign-off —
are **not implemented today**. Current `audit-grade` is "more rounds + stricter convergence +
the gate." Do not promise the roadmap behaviors to the user.
