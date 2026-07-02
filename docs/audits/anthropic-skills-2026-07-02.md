# Library audit — Anthropic's official skills (anthropics/skills)

What does the temper audit say about the 17 skills in
[anthropics/skills](https://github.com/anthropics/skills)? One command:

```bash
temper-skills audit skills/ --report audit.md   # 17 skills, one judge turn each
```

Run 2026-07-02, `vertex_ai/claude-sonnet-4-6`. **Headline: none is a clean freeze
candidate — and that's the audit doing its job.** These are document/creative skills;
the audit routes them away from tempering instead of burning the loop on them. What it
*did* find: **11 of 17 bundle 2–5 separable decisions** inside one prompt, re-derived
on every call.

| skill | verdict | bundled decisions | recommended fix |
| --- | --- | --- | --- |
| `claude-api` | SPLIT FIRST | 4 | `decompose` |
| `internal-comms` | SPLIT FIRST | 2 | `decompose` |
| `docx` | SPLIT FIRST | 2 | `decompose` |
| `pdf` | SPLIT FIRST | 2 | `decompose` |
| `pptx` | SPLIT FIRST | 3 | `decompose` |
| `skill-creator` | SPLIT FIRST | 5 | `decompose` |
| `webapp-testing` | SPLIT FIRST | 2 | `decompose` |
| `theme-factory` | SPLIT FIRST | 3 | `decompose` |
| `brand-guidelines` | SPLIT FIRST | 3 | `decompose` |
| `canvas-design` | SPLIT FIRST | 2 | `decompose` |
| `doc-coauthoring` | SPLIT FIRST | 4 | `decompose` |
| `xlsx` | SPLIT FIRST | 2 | `decompose` |
| `mcp-builder` | SPLIT FIRST | 4 | `decompose` |
| `frontend-design` | NOTHING TO FREEZE | — | `delegate_prose` |
| `web-artifacts-builder` | SPLIT FIRST | 2 | `decompose` |
| `algorithmic-art` | NOTHING TO FREEZE | — | `delegate_prose` |
| `slack-gif-creator` | NOTHING TO FREEZE | — | `delegate_prose` |

## What the judge actually said (selected rationale, verbatim)

- **claude-api** — The skill ultimately routes to a finite set of surfaces (Claude API, Managed Agents, Batch, Files, Streaming, Tool Use, migration, etc.) and language-specific files — but a huge portion of its execution is open-ended code generation, so it's a mix: real routing decisions exist but generation dominates the output.
- **skill-creator** — The skill is overwhelmingly generative — drafting skills, writing instructions, producing test cases, synthesizing feedback — with only a few routing forks (Claude.ai vs. Claude Code vs. Cowork, new vs. existing skill). No finite verdict or classification dominates.
- **slack-gif-creator** — The skill is almost entirely open-ended generative output — it produces custom animation code and pixel art for arbitrary user prompts; there is no finite verdict or routing outcome to freeze.
- **internal-comms** — Routes to one of four finite template files (3P, newsletter, FAQ, general), which is a clear finite outcome set — but the bulk of the work after routing is open-ended drafting/generation.

## Takeaways

- **The audit says no most of the time.** 6/17 have nothing to freeze (creative or
  prose skills → `delegate_prose`); none scored a clean `temper`. A triage tool that
  recommended tempering everything would be selling, not triaging.
- **Implicit decision bundling is the norm, not the exception.** 11/17 hold 2–5
  separable decisions (`skill-creator`: 5, `claude-api`: 4) — each an untested branch
  point living in prose. `decompose` splits them; each split decision gets its own
  test suite even when the tree isn't worth it.
- **Decision-shaped skills live elsewhere.** Routing/triage/escalation playbooks —
  support routing, compliance gates, on-call escalation — are where `temper` verdicts
  come from (see `examples/`). Auditing a community corpus is the natural follow-up.

Reproduce: any backend works — `uvx temper-skills audit <dir>` with an
`ANTHROPIC_API_KEY` or a logged-in `claude` CLI.
