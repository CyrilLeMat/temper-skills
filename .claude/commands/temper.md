---
description: Temper a skill.md into a deterministic decision tree via the adversarial subagent loop
---

Use the **temper-skills** skill to compile the decision logic of `$ARGUMENTS` into a
deterministic Python decision tree.

Run the adversarial loop on the Claude Code subscription using persona subagents:
draft the tree, critique it each round with the five personas (in parallel), arbitrate
and show the scored round panel, gate with the user, and converge when every persona
scores ≥ 8 with no new gray zone. Then export the tree deterministically with
`python -m temper_skills.export_tree`.
