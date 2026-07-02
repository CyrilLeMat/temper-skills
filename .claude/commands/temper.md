---
description: Temper a skill.md into a test suite + deterministic decision tree via the adversarial subagent loop (a directory gets the ranked library audit)
---

Use the **temper-skills** skill to compile the decision logic of `$ARGUMENTS` into a
deterministic Python decision tree plus its adversarially-written validation dataset.
If `$ARGUMENTS` is a directory, run the skill's library sweep instead: audit every skill
in it and present the ranked findings table before tempering anything.

Run the adversarial loop on the Claude Code subscription using persona subagents:
draft the tree, critique it each round with the five personas (in parallel), arbitrate
and show the scored round panel, gate with the user, and converge when every persona
scores ≥ 8 with no new gray zone. Then export the tree deterministically with
`python -m temper_skills.export_tree`.
