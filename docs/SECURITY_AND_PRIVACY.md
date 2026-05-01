# Security and Privacy Notes

Updated: 2026-05-01.

`mew` persists agent state and runs guarded local automation. That makes it
more useful for long-running work, but also creates security-sensitive surfaces.
This document is a concise review map, not a complete third-party audit.

## Data Stored Locally

By default, mew stores runtime and memory artifacts under `.mew/` in the local
workspace. Depending on commands used, local artifacts may include:

- task state and questions
- typed memory and compact context checkpoints
- work-session summaries, tool calls, and model-turn metadata
- runtime effects and recovery notes
- approval decisions, dry-run write previews, and verification outcomes
- journal, dream, mood, bundle, desk, and other local companion artifacts

These files can contain project-sensitive paths, command output, model
summaries, and user-provided text. Treat `.mew/` as local private state unless
you intentionally publish selected artifacts.

## Secrets and Auth

Auth files such as `auth.json`, `auth.plus.json`, `.env`, provider tokens, and
API keys should not be committed. The runtime and work-loop documentation
expects auth paths to be passed explicitly when model access is needed.

Recommended operator practice:

- keep provider auth outside committed source where possible
- review `git status` before committing
- avoid pasting secrets into tasks, questions, memory, or work guidance
- inspect model-visible context when debugging sensitive failures

## Tool and Side-Effect Boundaries

mew separates local actions behind explicit gates:

- read access requires allowed read roots in native work sessions
- file writes default to dry-run previews
- applied writes require explicit write permission and should be paired with
  verification when product code changes
- shell/test execution is gated separately from ordinary reads
- launcher execution is opt-in and dry-run by default in side-project surfaces
- webhook ingress requires loopback binding or an explicit token for
  non-loopback serving
- external-visible actions such as push, merge, issue comments, publication,
  and messaging should remain human-approved

The project intentionally records failed or interrupted side effects so that
future agents and humans can decide whether retry, rollback, or stop is safe.

## Persistent Memory Risks

Durable memory can accidentally preserve stale, sensitive, or over-broad
context. mew mitigates this by using typed/scoped memories, compact checkpoints,
stale markers, recovery plans, and explicit context-save/load commands, but
operators should still review what is written before sharing artifacts.

Risks to watch:

- stale plan text being mistaken for current intent
- sensitive command output entering model-readable summaries
- persisted paths revealing private workspace structure
- broad memory recall pulling in irrelevant or private context
- benchmark or dogfood artifacts containing auth-related failure text

## Benchmark and Dogfood Artifacts

Terminal-Bench, side-project dogfood, and repair ledgers are designed to be
public evidence, but they can still include local paths, command summaries, and
model-visible task context. Before publishing a new packet, review:

- `proof-artifacts/*.jsonl`
- `docs/M6_24_*`
- `experiments/*/.mew-dogfood/reports/*.json`
- work-session reports written to `/tmp` or local artifact folders

## Codex Security Review Targets

If mew receives Codex Security access, the narrow useful review targets are:

- persisted `.mew/` state, typed memory, and snapshots
- prompt/context construction and active-memory injection
- work-session write, shell, verification, and recovery gates
- auth file path handling and accidental secret capture
- webhook and notification surfaces
- launcher intent execution and dry-run boundaries
- benchmark/dogfood artifact publication workflow

## Current Limitations

- This document is an operator note, not a formal security policy.
- mew is early and has not had a full external security audit.
- The safest deployment model is local, single-user, explicit-gate operation.
- Any broader multi-user, daemon, webhook, or background-monitoring use should
  require a fresh threat model and review before adoption.
