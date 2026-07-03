# Reference

The deep dives the [README](../README.md) links to. Same order as the README sections.

## The audit's axes and actions

Under the audit's findings sit four scored axes:

- **decisiveness** — does it resolve to a finite verdict, or is it open-ended generation?
- **combinatorics** — is the hardness in feature *interactions*, or a flat unbounded lookup?
- **stakes** — is it repeated/auditable enough that freezing pays off?
- **schema closure** *(computed, not judged)* — what share of the features pin to a bounded
  value space? Free-text fields leak into the normalizer you own.

The three judged axes come from **one LLM call**; the findings and the recommended action are
**pure functions** of the four, so the audit is as reproducible and explainable as the tree it
gates. The same call also reports `distinct_decisions` — when it's ≥2, the skill is a flow and
the action becomes `decompose`.

| Action | When | Who does it |
| --- | --- | --- |
| `temper` | decisive + closed schema | **us** — the loop |
| `decompose` | ≥2 separable decisions | **us** — `decompose` |
| `externalize_data` | flat lookup keyed on free text | **us** (small) — a data file + matcher |
| `build_normalizer` | real logic but un-pinned text inputs | upstream, yours (Instructor / your extractor) |
| `delegate_prose` | no decision — it's generation | **delegate** → `skill-creator`, DSPy |

That last column is the point: temper **owns the decision-freezing lane** and **delegates the
commodity** (improving prose, generating generic evals) to tools that already do it well —
rather than being a mediocre everything-tool. The audit is the triage front door.

Exit codes: 0 when anything is actionable, 3 when everything is a skip — pipeline-friendly.

## Personas and profiles

- `literalist` — exploits ambiguities in the schema
- `edge_case_hunter` — finds rare input combinations
- `bad_faith_actor` — tries to circumvent the rules
- `domain_expert` — tests with plausible domain cases
- `overengineering_critic` — challenges every node: "is this branch actually necessary?" (always on)
- `schema_critic` / `outcome_critic` — argue the schema/outcome set is too thin to express the
  source (standard & audit-grade); they drive the co-evolving schema.

The panel scales with profile — more personas of one model share blind spots and add cost +
convergence surface, so cheap runs stay lean and the full panel is reserved for `audit-grade`.
Override per run with `distill(adversaries=[...])`. `bad_faith_actor` is reserved for
audit-grade because it earns its keep on circumvention-sensitive domains (routing,
compliance), less so on low-stakes ones.

## Backends

`--backend auto` uses `ANTHROPIC_API_KEY` if set, else a detected agent CLI (`claude`,
`opencode`). The API backend runs on **LiteLLM + Instructor**, so `--model` takes any LiteLLM
id (`claude-sonnet-4-6`, `openai/gpt-4o`, `gemini/gemini-1.5-pro`, a local model, …) with the
matching provider key in the environment — provider integration and structured-output parsing
aren't ours.

Note: headless agent CLIs (`claude -p`) bill the **API**, not your subscription — for a
subscription-billed run use the Claude Code subagent mode (`/temper`).

**Claude on Vertex AI (GCP billing, no Anthropic key):** `pip install "temper-skills[vertex]"`,
`gcloud auth application-default login`, then
`export VERTEXAI_PROJECT=<project> VERTEXAI_LOCATION=<region>` and run with
`--backend api --model vertex_ai/<claude-id>`. Requires Claude enabled in your Vertex Model
Garden for that project/region.

## Bootstrapping the schema — draft, ratify, freeze

You don't have to write `schema.py` from a blank page. `--propose-schema` reads the skill,
drafts the feature set as editable Pydantic source, surfaces each field's **normalization
burden**, and then *stops* — it never distills on an unratified contract:

```bash
temper-skills ingest skill.md --propose-schema   # writes schema.proposed.py, then stops
# review/edit the fields (rename, fix a type, tighten a str into Literal[...]), then:
temper-skills ingest skill.md --schema schema.proposed.py:RouteTicket
```

The schema is the contract the determinism guarantee rests on, so the loop only ever runs on
one a human has pinned — same draft → ratify → freeze lifecycle as proposed examples. The
draft flags exact-match `str` fields (whose safety lives in *your* normalizer) and enum-like
ones (where a `Literal` closes the space and helps the loop converge).
`decompose --emit-schemas` is the same lifecycle, one mini-schema per decision.

## The tempered skill

`ingest` emits a **tempered `skill.md`** that delegates the decision to the tree, so the
original prompt actually adopts the frozen logic instead of re-deriving it every call. It
keeps the model's real jobs — turning the request into structured features and phrasing the
answer — and freezes the *decision*:

> **The decision is frozen.** Extract `food_item` from the request, call
> `from dog_food_checker import can_dog_eat`, relay the verdict, don't override it. Gray
> zones to surface: …

By default it's a **deterministic template** (no LLM), carrying the recorded gray zones
forward as caveats. Pass `--skill-style woven` to instead have the model rewrite the original
skill *in its own voice* — same delegation contract, nicer prose, at the cost of a model call
(falls back to the template if the call fails). For a flow, the orchestrator is the same idea
over *several* trees — see
[`examples/dog_day/output/dog-day/SKILL.md`](../examples/dog_day/output/dog-day/SKILL.md).

## The validation lifecycle

The loop **always builds a validation set** (on by default; `--no-propose-examples` to skip).
Every round, each persona except the structural critics contributes the concrete cases it
found — a full input plus the outcome it believes correct — deduped across rounds. This rides
along in the critiques the panel already produces, so it costs no extra model calls.

**The loop scores the tree against these cases each round** — to pick the best tree and to
decide convergence. That's not self-grading: the labels are written by the **adversarial
personas**, not the proposer, so it's "satisfy your critics." Ratified examples, when you
supply them, rank *ahead* of the proposed ones and are never traded away to match a proposed
label.

```
✎ validation dataset (awaiting ratification)
  input={'priority': 'urgent', 'security_score': 0.85}  — edge_case_hunter (round 4)
    proposed escalate_urgent  ·  tree says escalate_security   (differs from tree)
→ dataset → route_ticket.validation.jsonl · behavior-lock → test_route_ticket.py (1 open disagreement)
```

Each case is tagged `"status": "proposed"`; `load_dataset` *ignores* proposed entries, so they
never silently become a CI gate. The committed behavior-lock test asserts only what the tree
returns (always green); a disagreement is an `"agrees": false` row in the dataset, never a
failing or xfail test. Review the labels, set `"status": "ratified"`, and on the next run they
become authoritative ground truth the loop must honor. That's how an empty validation set
grows into a trusted one.

At compile time, any ratified `examples` you anchor with
(`--examples ratified.json` / `Sources(examples=[...])`) are checked automatically and exit
non-zero below `--min-agreement` (default 1.0) — a real correctness gate, not prompt
seasoning. Optional for a demo; **mandatory** for high-stakes domains — a tree shipped without
a held-out set is not auditable, no matter how many rounds it survived.

## Out of scope: normalization

The tree branches on *pre-computed structured features*; turning raw input ("a slice of dark
chocolate cake") into those features (`food_item="chocolate"`) is **upstream and out of
scope** — the `build_normalizer` audit lane is exactly when extraction, not the tree, is the
work. The determinism guarantee starts *after* that step:

```python
# Out of scope of the guarantee — a lightweight layer YOU own, before the tree:
def normalize(raw: str) -> dict:
    text = raw.strip().lower()
    item = next((t for t in KNOWN_FOODS if t in text), text)  # your extraction
    return {"food_item": item}

can_dog_eat(normalize("a slice of Dark Chocolate cake"))   # -> "no — toxic, never feed"
```
