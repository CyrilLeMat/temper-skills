# temper-skills — distributable agent skills

Temper-Skills ships as an **agent skill** in two modes. They are mutually exclusive — pick by
the host the agent runs in. Both turn a skill/prompt's decision logic into a deterministic,
versionable decision tree; they differ only in *how* they run the adversarial loop.

| | **subagent-mode** | **lib-wrapper** |
|---|---|---|
| Location | [`.claude/skills/temper-skills/`](../.claude/skills/temper-skills/) | [`skills/temper-skills/`](temper-skills/) |
| Host | Claude Code (anything with a Task/subagent primitive) | Cursor, Hermes, generic agents — **no** subagent primitive |
| Runs the loop via | the agent itself: proposer + persona **subagents** (Task tool) | the installed **`temper-skills` CLI** |
| Needs | nothing — runs on the Claude Code subscription | `pip install temper-skills` + a model backend (`claude`/`opencode` CLI, or an API key) |
| `allowed-tools` | `Task, Bash, Read, Write` | `Bash, Read, Write` |

## Which one

- **In Claude Code** → subagent-mode. It runs keyless on your subscription and streams a live
  per-round panel; no install. The presence of `Task` in its `allowed-tools` is the tell.
- **In any other agent** → lib-wrapper. It drives the CLI (never reimplements the logic),
  leads with `temper-skills guide` (audit-first triage), honors the schema gate via the
  file-based `--propose-schema` stop, and refuses to act until a backend is available.

The two `description` fields are written to be mutually exclusive ("inside Claude Code, no
install" vs "agents without a subagent primitive, requires install + backend"), so an agent
that somehow sees both will not fire the wrong one. Distribute them to different channels
accordingly.

## Status

Wave 2 — **design complete, not published.** Both skills are validated structurally and with
live end-to-end runs (single-decision `ingest` and flow `decompose` via `guide`). Publishing
(GitHub repo → Skills Hub / skills.sh → ClawHub) is gated on the library being live on PyPI
with first feedback.
