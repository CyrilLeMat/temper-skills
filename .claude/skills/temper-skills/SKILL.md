---
name: temper-skills
description: Compile an agent's decision logic (a prompt or skill.md) into a deterministic, versionable Python decision tree via an adversarial multi-persona loop — run entirely on your Claude Code subscription using subagents, no API key. Use when the user wants to "temper", "distill", "freeze", or "harden" the routing/decision logic of a skill, prompt, or playbook into testable code, or asks to turn a skill.md into a decision tree.
---

# Temper-Skills (subagent mode)

Turn the decision logic living in a prompt/`skill.md` into a **deterministic Python
decision tree** — readable, diffable in a PR, zero LLM calls at inference. You (the
orchestrator) act as the **proposer**; **persona subagents** are the adversarial
reviewers. Everything runs on the user's Claude Code subscription via the Task tool.

> "Adversarial" here means **decision robustness** — challenging business logic — not
> security scanning. The loop measures internal consistency, not correctness against the
> world; real correctness still comes from the user's ratified examples.

## Inputs

- A target `skill.md` / prompt (the logic to migrate), path given by the user.
- A **schema**: the pre-computed structured features the tree may branch on. If the user
  doesn't supply one, infer it from the skill (feature name + type + one-line meaning) and
  **show it for confirmation before looping**.
- Optional `hard` constraints (non-negotiable rules) and a few ratified examples.

Branch only on schema features. Conditions are valid Python boolean expressions over the
feature names (e.g. `food_item == "chocolate"`).

## The personas

Four attackers plus one always-on counterweight. Spawn **one subagent per persona each
round**, in parallel (one message, multiple Task calls). Keep each subagent prompt **lean
and self-contained** — do not make them read this skill or the repo.

| persona | angle |
|---|---|
| `literalist` | exploits literal ambiguities in the schema/conditions (casing, synonyms, None) |
| `edge_case_hunter` | seeks rare combinations of feature values the tree mishandles |
| `bad_faith_actor` | tries to strategically circumvent the rules |
| `domain_expert` | tests with rare-but-plausible domain cases; mobilizes public domain knowledge |
| `overengineering_critic` | **always on** — challenges every node: is this branch real domain complexity or loop richness? would an expert hand-write it? |

Each persona subagent returns ONLY this JSON:
```json
{"persona": "<name>", "score": 0-10, "verdict": "ok|missing_case|collapsible|contradiction",
 "detail": "<one sentence>", "proposed_case": "<concrete feature assignment it mishandles, or null>"}
```

## The loop

1. **Draft** the initial tree yourself (proposer) from the skill + schema + constraints.
   Cover obvious cases; flag genuinely ambiguous regions as `gray_zone` rather than guessing.
2. **Critique** — spawn the 5 persona subagents in parallel with the current tree; collect
   their scored JSON verdicts.
3. **Arbitrate** (proposer) — for each persona decide `kept` / `changed` / `rejected` with a
   one-line rationale (this is the *arbitrage log*). Then revise the tree: add a branch only
   if a critique justifies it AND an expert would write it by hand; collapse branches the
   `overengineering_critic` flags. Never contradict a HARD constraint. Track
   `rounds_survived` per node (matched by condition).
4. **Show the round panel** — round N, per-persona `score/10` (sorted worst-first), the
   arbitrage log, current tree preview, and `min/mean` score.
5. **Gate** — ask the user: Continue · Stop and review · Abort. (Skip the gate only if they
   asked for an unattended/quick run.)
6. **Converge** — stop when **every persona scores ≥ 8 AND no new gray zone appeared** for
   the round, or the user stops, or you hit the round cap (`quick` ~8, `standard` ~20).

## Export (deterministic — no LLM)

When the loop ends, write the tree to JSON and run the deterministic exporter:

```bash
python -m temper_skills.export_tree tree.json route.py
```

The tree JSON shape:
```json
{
  "fn_name": "can_dog_eat",
  "features": ["food_item", "food_form", "dog_weight_kg"],
  "default_outcome": "unknown — verify manually",
  "model": "claude-<model> via claude-code-subagents",
  "profile": "standard",
  "nodes": [
    {"condition": "food_item == \"chocolate\"", "outcome": "toxic — never",
     "rounds_survived": 14, "sources": ["domain_expert", "constraints#1"],
     "gray_zone": null, "critic_note": null}
  ]
}
```

The exported `route.py` carries a `generated_at` + `model` header (mandatory — a tree
without a timestamp is not auditable), one inline provenance comment per node, and gray
zones as trailing comments. It imports nothing and makes zero LLM calls at inference.

## Complexity contract

The output must read like a tree a domain expert would hand-write. Tree depth/node count
should reflect domain complexity, not how many rounds the loop ran. If you wouldn't accept
the tree in a code review, it's over-engineered — let the `overengineering_critic` win that
round. Provenance lives in comments, never in logic.
