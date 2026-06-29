# Support-ticket routing — the combinatorial example

This is the example to watch the loop **converge**. Unlike a toxic-food list (a flat,
unbounded lookup the loop thrashes on), ticket routing has a **closed feature space** —
enums + a bounded score + a bool — where the difficulty is the *interactions*
(priority × tier × SLA × security), exactly the "combinatorially hard" sweet spot the tool
is for. The `overengineering_critic`'s pressure is productive here (collapse redundant
branches), not unsatisfiable (there's no infinite item list to enumerate).

```
input/
  skill.md                a triage prompt: escalate security, prioritize paying tiers, route by category
output/
  schema.py               TicketSchema — priority, security_score, customer_tier, category, sla_breached
  validation_set.json     18 ratified cases exercising the interactions + a None security_score
  route_ticket_tree.json  provenance
  route_ticket.py         the deterministic router — zero LLM at inference
  skill.tempered.md       a triage skill that calls the router
```

## Run it

```bash
# subscription, no key:
/temper examples/ticket_routing/input/skill.md

# library / CLI (pin the schema so the tree matches the validation set):
temper-skills ingest examples/ticket_routing/input/skill.md --backend auto --profile standard -y \
  --schema examples/ticket_routing/output/schema.py:TicketSchema --fn route_ticket \
  --out examples/ticket_routing/output/route_ticket.py \
  --examples examples/ticket_routing/output/validation_set.json
```

## What the loop finds (and why it converges)

The source prose says "prioritize paying customers" and "escalate SLA breaches" — the loop
turns those into explicit **interactions** the prompt only implied:

- `priority == "high" and customer_tier in ("pro","enterprise")` → escalate (high + free does *not*)
- `sla_breached and customer_tier != "free"` → escalate (a breached SLA escalates only for paying tiers)
- `security_score > 0.95` → human_review, overriding every routing rule (the hard constraint)
- a 0.8 security cut that beats category routing (a high-score billing ticket still goes to security)

Because the features are closed sets, `domain_expert` runs out of genuinely-new cases and
`overengineering_critic` collapses the category one-liners into the default — so scores
**stabilize** and the loop converges (7 nodes), instead of oscillating forever.

## Verify (§4.5)

```bash
temper-skills validate examples/ticket_routing/output/route_ticket.py \
  examples/ticket_routing/output/validation_set.json --fn route_ticket --match exact
# Agreement: 18/18 (100.0%)
```

Pinned in CI by `tests/test_validate.py`.
