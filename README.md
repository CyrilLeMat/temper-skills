# Temper-Skills

[![CI](https://github.com/CyrilLeMat/temper-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/CyrilLeMat/temper-skills/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CyrilLeMat/temper-skills/python-coverage-comment-action-data/endpoint.json)](https://github.com/CyrilLeMat/temper-skills/tree/python-coverage-comment-action-data)
[![PyPI](https://img.shields.io/pypi/v/temper-skills)](https://pypi.org/project/temper-skills/)
[![Python](https://img.shields.io/pypi/pyversions/temper-skills)](https://pypi.org/project/temper-skills/)
[![License](https://img.shields.io/github/license/CyrilLeMat/temper-skills)](LICENSE)

> Your skill is silently making decisions. Temper-Skills finds them, gets adversarial
> reviewers to write a **test suite** for them, and freezes the logic into deterministic
> Python that must keep passing.

A skill or prompt is usually a *flow*: a few decisions (classify, route, escalate, judge)
tangled with generation — re-derived from prose on every call, with no tests. Temper-Skills
gives that decision logic what code gets: **a reviewed, labeled test suite** (written by
adversarial persona reviewers, not by the model grading itself) and **a deterministic
implementation** — readable Python you can diff in a PR and pin in CI, with **zero LLM calls
at inference**.

Does the review actually catch anything? Fed a first-aid skill giving outdated **RICE**
advice, the panel **corrected its own source** — see [Step 3](#step-3--temper-freeze-one-decision-into-tests--a-tree).

## Quickstart

```bash
uvx temper-skills audit path/to/skill.md    # one skill: findings + a recommended fix
uvx temper-skills audit .claude/skills/     # your whole library, ranked (--report audit.md to share)
```

![A live audit of the flagship example — real run, unedited](docs/assets/audit-demo.gif)

No config. Any one backend works — an `ANTHROPIC_API_KEY` or a logged-in `claude`/`opencode`
CLI — and it tells you exactly what to do if none is found. Inside **Claude Code** there's
nothing to install: [`/temper path/to/skill.md`](#two-ways-to-run-it) runs on your
subscription. Bare `temper-skills <path>` does the right thing: a directory gets the library
sweep, a file gets the guided tour.

```
skill.md ──audit──▶ findings + recommended fix
                      ├─ temper           → run the loop: test suite + deterministic tree
                      ├─ decompose         → it's a flow: split into N decisions, temper each
                      ├─ externalize_data  → flat lookup: emit a data file + matcher, not a tree
                      ├─ build_normalizer  → real logic on free-text input: pin the features first
                      └─ delegate_prose    → no decision here: improve it as prose elsewhere
```

Three steps — **audit → (decompose) → temper** — and you can stop after any of them.

## Step 1 — `audit`: what is this skill deciding?

A health report for a skill's decision logic — worth reading even if you never temper. It
names the decision, reports findings in plain terms (implicit decisions bundled together,
free-text inputs whose answers drift call-to-call, lookup tails wearing a tree's clothes),
and recommends a fix per finding — tempering is one of five possible fixes, not the premise.
Temper owns the decision-freezing lane and **delegates the rest** (prose quality, generic
evals) to tools that already do it well.

```bash
temper-skills audit skill.md --report audit.md   # findings + a shareable Markdown report
```

→ the four scored axes, the action table, and exit codes: [docs/reference.md](docs/reference.md#the-audits-axes-and-actions)

## Step 2 — `decompose`: a flow into its decisions

The loop freezes *one* decision at a time, so a multi-decision skill is split first into
per-decision mini-schemas plus the generative steps left to the model. `--temper-each` runs
the whole chain: it emits the schemas, **stops for you to ratify them**, then on re-run
tempers each into a tree and writes a thin orchestrator skill that chains them.

```bash
temper-skills decompose skill.md --temper-each --out-dir out/   # emit + stop; re-run to compile
```

See [`examples/dog_day/`](examples/dog_day/) — a dog-care assistant split into three chained
decisions + a note.

## Step 3 — `temper`: freeze one decision into tests + a tree

This is the engine. An **adversarial loop** reviews the decision from several angles — a
proposer drafts the tree, personas attack it, an independent arbiter rules on each critique —
and converges when no round improves on the best.

The flagship example, [`examples/ankle_sprain/`](examples/ankle_sprain/): the source skill
advises the **outdated RICE protocol**. The panel — drawing on medical literature the prompt
never cited — **corrects its own source** and layers in the Ottawa fracture rules the prompt
never mentioned *(educational example, not clinical advice)*:

```
✓ 16-case test suite → test_assess_ankle_ratified.py  ·  16/16 ratified cases pass
✓ deterministic tree → assess_ankle.py  (zero LLM calls at inference)
✓ tempered skill → ankle-sprain/SKILL.md  (now advises PEACE & LOVE, not RICE)
```

```python
# assess_ankle.py — generated by temper-skills (audit-grade) — excerpt
def assess_ankle(case: dict) -> str:
    ...
    # critic: the Ottawa Ankle Rule — 5 interacting criteria that rule fracture in/out;
    # this is the combinatorics a flat 'is it broken?' check misses
    if pain_malleolar_zone is True and (bone_tenderness_lateral_malleolus is True
            or bone_tenderness_medial_malleolus is True or can_bear_weight is False):
        return 'seek_imaging'
    ...
    # critic: OH-MERDE: the source skill said RICE + complete rest + heavy icing — that's
    # outdated since ~2012. Acute phase is PEACE: Protect, Elevate, Avoid prolonged ice
    # (it slows healing), Compress, Educate — early protected loading, NOT complete rest
    if hours_since_injury is not None and hours_since_injury <= 72:
        return 'police_acute'
```

The correction isn't prose in a chat window — it's a reviewed, versioned diff: the tree
disagrees with its own source, says why in a provenance comment, and 16 ratified cases pin
the corrected behavior in CI forever.

| Profile | Max rounds | Panel | Per-round gate |
| --- | --- | --- | --- |
| `quick` | ~8 | 1 attacker + critic | no — draft output |
| `standard` | ~20 | 2 attackers + 3 structural critics | yes |
| `audit-grade` | ~50 | 4 attackers + 3 structural critics | yes |

→ who the personas are and why the panel scales: [docs/reference.md](docs/reference.md#personas-and-profiles)

## Two ways to run it

**1. On your Claude Code subscription — no install, no API key.** The
[subagent-mode skill](.claude/skills/temper-skills/) drives the loop with persona subagents:

```
/temper path/to/skill.md
```

**2. As a CLI / library — any LiteLLM backend** (Anthropic, OpenAI, Gemini, Vertex, local),
for CI and headless use:

```bash
temper-skills ingest skill.md --backend auto     # api | claude | opencode | auto
```

```python
tree = temper_skills.distill(
    sources=temper_skills.Sources(
        schema=AnkleInjury,
        constraints=[{"rule": "visible_deformity -> always urgent_care", "hard": True}],
    ),
    profile="audit-grade",
)
tree.export("assess_ankle.py")
```

→ backend selection, billing caveats, Vertex AI setup: [docs/reference.md](docs/reference.md#backends)

## The guarantees, and where they stop

- **The schema is a ratified contract.** `--propose-schema` drafts it from the skill and
  *stops* for your review — the loop never runs on an unratified schema.
  [→ details](docs/reference.md#bootstrapping-the-schema--draft-ratify-freeze)
- **The test suite grows as the loop runs.** Personas contribute labeled cases every round
  (deduped, written to disk with provenance); proposed labels never gate CI until a human
  ratifies them. `temper-skills validate tree.py cases.json` pins the tree in CI — a prompt
  can't be. [→ the full lifecycle](docs/reference.md#the-validation-lifecycle)
- **The original skill adopts the tree.** A tempered `skill.md` is emitted that extracts
  features, calls the frozen function, and relays the verdict — instead of re-deriving the
  logic every call. [→ details](docs/reference.md#the-tempered-skill)
- **Trees evolve without recompiling.** `temper-skills incremental tree.json -c "<new rule>"`
  re-crystallizes around the delta and shows a reviewable structural diff; untouched nodes
  keep their provenance.
- **Not a security scanner, not an extractor.** "Adversarial" means decision robustness, not
  prompt injection; and turning raw text into the schema's features is a small normalizer
  *you* own, upstream of the guarantee. [→ scope](docs/reference.md#out-of-scope-normalization)

## Where this fits

**Not another skill eval harness — the step after one.** Eval harnesses like
[skillgrade](https://github.com/mgechev/skillgrade) and
[agent-skills-eval](https://github.com/darkrishabh/agent-skills-eval) measure the *model
wielding the skill*: run the task N times with graders, or A/B the same prompts with and
without the skill loaded. That's the right tool for prose, generation, and tool-flow
quality — and it's measurement, not change: after the eval, every production call still
re-derives the skill's decisions from prose, so the number you measured can drift with the
next model bump or prompt tweak. Temper-Skills takes the *decision* subset of the skill out
of that loop entirely — into Python that can't drift and ratified cases that gate it in CI.
Use both: a harness for "does the model use this skill well?", temper for the
classify/route/escalate calls that shouldn't be re-decided on every call.

**Real sweep:** [docs/audits/anthropic-skills-2026-07-02.md](docs/audits/anthropic-skills-2026-07-02.md)
audits Anthropic's 17 official skills — none is a clean freeze candidate (the audit says no
most of the time; that's the point), but 11 of 17 bundle 2–5 separable decisions in one
prompt. In a system that evolves skills automatically (e.g. SkillClaw), the audit is the
triage: crystallize what's worth crystallizing, decompose the flows, delegate the prose.

## Examples

- [`examples/ankle_sprain/`](examples/ankle_sprain/) — **the flagship — start here.** The
  source prompt gives outdated **RICE** advice; the loop corrects it to **POLICE /
  PEACE & LOVE** and layers in the Ottawa Ankle Rules the prompt never mentioned. The proof
  that the panel isn't theater. Educational only, not clinical advice. Audit: **TEMPER**.
- [`examples/ticket_routing/`](examples/ticket_routing/) — **the one to watch converge.** A
  closed feature space where the difficulty is the *interactions* (priority × tier × SLA ×
  security). The loop's sweet spot. Audit: **TEMPER**.
- [`examples/parking/`](examples/parking/) — **the everyday good fit.** Zone × day × hour ×
  holiday × permit, with the edges a flat reading misses. Audit: **TEMPER**.
- [`examples/license_compat/`](examples/license_compat/) — **the "moat" demo.** OSS license
  compatibility: genuinely hard combinatorics. Audit: **TEMPER** (audit-grade).
- [`examples/dog_food/`](examples/dog_food/) — **the cautionary contrast.** A flat lookup
  with an unbounded toxin tail — the toxin list wants to be a data file, not a tree.
  Audit: **CAVEATS** → `externalize_data`.
- [`examples/dog_day/`](examples/dog_day/) — **the flow.** Three decisions + a note →
  three trees + a thin orchestrator. Audit: **DECOMPOSE FIRST**.

## Honest scope

- **Built and tested:** `audit` (single skill or library sweep), `decompose`, the adversarial
  `temper` loop, `validate`, incremental mode, the tempered-skill emitter.
- **Deferred:** the `clarify`/`generate_examples` actions; a woven `--temper-each`
  orchestrator; `audit_decision` can over-count decisions on an already-atomic skill.
- **`audit-grade`** today is `standard` with more rounds and stricter convergence —
  tournament orchestration, required citations, and per-gray-zone sign-off are roadmap.
- The `dog_day` trees are quick-profile drafts; harden with `standard`/`audit-grade` + a
  held-out set for real use.

## Development

```bash
pip install -e ".[dev]"
pytest -q                             # full suite, no network
git config core.hooksPath .githooks   # once per clone: block red commits locally
```

CI runs lint/format/types + the suite on Python 3.10–3.13, then `temper-skills validate` on
the canonical examples — the tool gating itself with its own command. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## Origin

Mechanism validated in production on medical tooling — deterministic rule engines built by
adversarial loop. Temper-Skills is the open-source generalization. Apache-2.0.
