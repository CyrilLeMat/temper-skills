<p align="center">
  <img src="https://raw.githubusercontent.com/CyrilLeMat/temper-skills/main/docs/assets/banner.png" alt="Temper-Skills — adversarial reviewers write a test suite for your agent skill's decision logic, then freeze it into deterministic Python" width="830">
</p>

<p align="center">
  <a href="https://github.com/CyrilLeMat/temper-skills/actions/workflows/ci.yml"><img src="https://github.com/CyrilLeMat/temper-skills/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/CyrilLeMat/temper-skills/tree/python-coverage-comment-action-data"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CyrilLeMat/temper-skills/python-coverage-comment-action-data/endpoint.json" alt="Coverage"></a>
  <a href="https://pypi.org/project/temper-skills/"><img src="https://img.shields.io/pypi/v/temper-skills" alt="PyPI"></a>
  <a href="https://pypi.org/project/temper-skills/"><img src="https://img.shields.io/pypi/pyversions/temper-skills" alt="Python"></a>
  <a href="https://github.com/CyrilLeMat/temper-skills/blob/main/LICENSE"><img src="https://img.shields.io/github/license/CyrilLeMat/temper-skills" alt="License"></a>
</p>

> Your skill is silently making decisions. Temper-Skills finds them, gets adversarial
> reviewers to write a **test suite** for them, and freezes the logic into deterministic
> Python that must keep passing.

<p align="center">
  <img src="https://raw.githubusercontent.com/CyrilLeMat/temper-skills/main/docs/assets/schema.png" alt="Before: a classic skill, its decisions buried in prose and re-derived on every call. The temper adversarial loop turns it into a light skill: a thin SKILL.md that delegates, a typed input contract you ratify, a deterministic assess_ankle.py with zero LLM calls, and a ratified test suite pinned in CI.">
</p>

Does the review actually catch anything? Fed a first-aid skill giving outdated **RICE**
advice, an audit-grade run **corrected its own source** — and the ratified suite pins that
correction so no later run can regress it — see [Step 3](#step-3--temper-freeze-one-decision-into-tests--a-tree).

## Quickstart

```bash
uvx temper-skills audit path/to/skill.md    # one skill: findings + a recommended fix
uvx temper-skills audit .claude/skills/     # your whole library, ranked (--report audit.md to share)
```

![A live run on the flagship example — audit, then the adversarial temper loop converging round by round; real run, waits compressed](https://raw.githubusercontent.com/CyrilLeMat/temper-skills/main/docs/assets/demo.gif)

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

→ the four scored axes, the action table, and exit codes: [docs/reference.md](https://github.com/CyrilLeMat/temper-skills/blob/main/docs/reference.md#the-audits-axes-and-actions)

## Step 2 — `decompose`: a flow into its decisions

The loop freezes *one* decision at a time, so a multi-decision skill is split first into
per-decision mini-schemas plus the generative steps left to the model. `--temper-each` runs
the whole chain: it emits the schemas, **stops for you to ratify them**, then on re-run
tempers each into a tree and writes a thin orchestrator skill that chains them.

```bash
temper-skills decompose skill.md --temper-each --out-dir out/   # emit + stop; re-run to compile
```

See [`examples/dog_day/`](https://github.com/CyrilLeMat/temper-skills/tree/main/examples/dog_day/) — a dog-care assistant split into three chained
decisions + a note.

## Step 3 — `temper`: freeze one decision into tests + a tree

This is the engine. An **adversarial loop** reviews the decision from several angles — a
proposer drafts the tree, personas attack it, an independent arbiter rules on each critique —
and converges when no round improves on the best.

The flagship example, [`examples/ankle_sprain/`](https://github.com/CyrilLeMat/temper-skills/tree/main/examples/ankle_sprain/): the source skill
advises the **outdated RICE protocol**. In the audit-grade run that produced these artifacts,
the panel — drawing on medical literature the prompt never cited — **corrected its own
source** and layered in the Ottawa fracture rules the prompt never mentioned *(educational
example, not clinical advice)*:

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
the corrected behavior in CI forever. That permanence is the point: an LLM re-derives this
logic on every call, and whether it recalls that RICE is outdated is a dice roll — re-run
the loop and it may converge back to RICE (the Ottawa gates reappear more reliably). A
prompt catches the correction *sometimes*; the loop only has to catch it **once** — ratify
it, and regressing to RICE stops being a bad sample and becomes a failing test.

| Profile | Max rounds | Panel | Per-round gate |
| --- | --- | --- | --- |
| `quick` | ~8 | 1 attacker + critic | no — draft output |
| `standard` | ~20 | 2 attackers + 3 structural critics | yes |
| `audit-grade` | ~50 | 4 attackers + 3 structural critics | yes |

→ who the personas are and why the panel scales: [docs/reference.md](https://github.com/CyrilLeMat/temper-skills/blob/main/docs/reference.md#personas-and-profiles)

## Two ways to run it

**1. On your Claude Code subscription — no install, no API key.** The
[subagent-mode skill](https://github.com/CyrilLeMat/temper-skills/tree/main/.claude/skills/temper-skills/) drives the loop with persona subagents:

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

→ backend selection, billing caveats, Vertex AI setup: [docs/reference.md](https://github.com/CyrilLeMat/temper-skills/blob/main/docs/reference.md#backends)

## The guarantees, and where they stop

- **The schema is a ratified contract.** `--propose-schema` drafts it from the skill and
  *stops* for your review — the loop never runs on an unratified schema.
  [→ details](https://github.com/CyrilLeMat/temper-skills/blob/main/docs/reference.md#bootstrapping-the-schema--draft-ratify-freeze)
- **The test suite grows as the loop runs.** Personas contribute labeled cases every round
  (deduped, written to disk with provenance); proposed labels never gate CI until a human
  ratifies them. `temper-skills validate tree.py cases.json` pins the tree in CI — a prompt
  can't be. [→ the full lifecycle](https://github.com/CyrilLeMat/temper-skills/blob/main/docs/reference.md#the-validation-lifecycle)
- **The original skill adopts the tree.** A tempered `skill.md` is emitted that extracts
  features, calls the frozen function, and relays the verdict — instead of re-deriving the
  logic every call. [→ details](https://github.com/CyrilLeMat/temper-skills/blob/main/docs/reference.md#the-tempered-skill)
- **Trees evolve without recompiling.** `temper-skills incremental tree.json -c "<new rule>"`
  re-crystallizes around the delta and shows a reviewable structural diff; untouched nodes
  keep their provenance.
- **Not a security scanner, not an extractor.** "Adversarial" means decision robustness, not
  prompt injection; and turning raw text into the schema's features is a small normalizer
  *you* own, upstream of the guarantee. [→ scope](https://github.com/CyrilLeMat/temper-skills/blob/main/docs/reference.md#out-of-scope-normalization)

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

**Real sweep:** [the audit of Anthropic's 17 official skills](https://github.com/CyrilLeMat/temper-skills/blob/main/docs/audits/anthropic-skills-2026-07-02.md) —
the audit says no most of the time (that's the point); 11 of 17 bundle 2–5 separable
decisions in one prompt.

## Examples

| Example | Why it's here | Audit |
| --- | --- | --- |
| [`ankle_sprain/`](https://github.com/CyrilLeMat/temper-skills/tree/main/examples/ankle_sprain/) | **The flagship — start here.** Outdated RICE advice corrected to PEACE & LOVE + the Ottawa rules, locked in by the ratified suite *(educational, not clinical advice)* | **TEMPER** |
| [`ticket_routing/`](https://github.com/CyrilLeMat/temper-skills/tree/main/examples/ticket_routing/) | The one to watch converge: the difficulty is the interactions (priority × tier × SLA × security) | **TEMPER** |
| [`parking/`](https://github.com/CyrilLeMat/temper-skills/tree/main/examples/parking/) | The everyday fit: zone × day × hour × holiday × permit, with the edges a flat reading misses | **TEMPER** |
| [`license_compat/`](https://github.com/CyrilLeMat/temper-skills/tree/main/examples/license_compat/) | The "moat" demo: OSS license compatibility, genuinely hard combinatorics | **TEMPER** (audit-grade) |
| [`dog_food/`](https://github.com/CyrilLeMat/temper-skills/tree/main/examples/dog_food/) | The cautionary contrast: an unbounded toxin list wants a data file, not a tree | **CAVEATS** → `externalize_data` |
| [`dog_day/`](https://github.com/CyrilLeMat/temper-skills/tree/main/examples/dog_day/) | The flow: three decisions + a note → three trees + a thin orchestrator | **DECOMPOSE FIRST** |

## Honest scope

- **Built and tested:** `audit` (single skill or library sweep), `decompose`, the adversarial
  `temper` loop, `validate`, incremental mode, the tempered-skill emitter.
- **The panel's insights are sampled, not guaranteed.** Structural attacks (edge cases,
  interaction bugs) recur reliably across runs; literature-level corrections like the RICE
  fix are opportunistic — a re-run may not rediscover one. The ratified suite is what turns
  a good run into a permanent one.
- **`audit-grade` proposes a lot to ratify.** One run on the flagship skill proposed 229
  cases with 65 open disagreements — budget a real review pass, or start with `standard`.
- Deferred features and roadmap:
  [docs/reference.md](https://github.com/CyrilLeMat/temper-skills/blob/main/docs/reference.md#deferred-and-roadmap)

## Development

```bash
pip install -e ".[dev]"
pytest -q                             # full suite, no network
git config core.hooksPath .githooks   # once per clone: block red commits locally
```

CI runs lint/format/types + the suite on Python 3.10–3.13, then `temper-skills validate` on
the canonical examples — the tool gating itself with its own command. See
[CONTRIBUTING.md](https://github.com/CyrilLeMat/temper-skills/blob/main/CONTRIBUTING.md).

## Origin

Mechanism validated in production on medical tooling — deterministic rule engines built by
adversarial loop. Temper-Skills is the open-source generalization. Apache-2.0.
