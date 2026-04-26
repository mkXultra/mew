# Mew Side Project Implementation Status

Last updated: 2026-04-26

This file is the compact operational dashboard for side-project implementation
dogfood. It is intentionally separate from `ROADMAP_STATUS.md`; the main
roadmap consumes side-project evidence through M6.13.2 and M6.16.

## Summary

| Milestone | Status | Current Meaning |
|---|---|---|
| SP0 Dogfood Harness Ready | `done` | Roadmap, status, `side-pj-mew-impl` skill, and M6.13.2 telemetry CLI are ready. |
| SP1 mew-companion-log Scaffold | `not_started` | First isolated implementation project has not been created yet. |
| SP2 Journal and Dream Reports | `not_started` | Companion report surfaces wait for SP1. |
| SP3 Implementation-Lane Evidence Cohort | `not_started` | Needs at least five recorded side-project attempts. |
| SP4 Optional Research Digest Slice | `not_started` | Deferred until SP1-SP3 produce useful evidence. |
| SP5 Feed M6.16 | `not_started` | Waits for enough side-project telemetry to name core implementation-lane bottlenecks. |

## Active Focus

Active side-project focus: **SP1 mew-companion-log Scaffold**.

Current target:

- keep side-project implementation mew-first
- use side-project Codex CLI as the `operator` that runs mew from the
  side-project directory and makes local decisions
- use Codex/Codex CLI as reviewer, comparator, or verifier when it is checking
  mew's work
- side-project Codex writes normal completion reports to a local report outbox;
  main Codex polls those reports and records accepted rows with
  `mew side-dogfood append`
- GitHub issues are only for problems: one real problem per issue, `[side-pj]`
  title prefix, open/closed state only, no label workflow in v0
- treat `proof-artifacts/side_project_dogfood_ledger.jsonl` as the primary
  evidence source for M6.16; reply/chat logs are auxiliary
- start `mew-companion-log`, not a GUI or OS-permission-heavy project

## Evidence

- Core M6.13.2 telemetry CLI exists:
  `mew side-dogfood template`, `mew side-dogfood append`, and
  `mew side-dogfood report`.
- Default ledger:
  `proof-artifacts/side_project_dogfood_ledger.jsonl`.
- `./mew side-dogfood report --json` returned a valid empty v0 telemetry
  report on 2026-04-26.
- `side-pj-mew-impl` skill exists at
  `.codex/skills/side-pj-mew-impl/SKILL.md`.
- First side project selected: `mew-companion-log`.
- First side project rationale: medium-sized, local-first, fixture-testable,
  product-relevant, and unlikely to hide implementation-lane failures behind
  GUI/platform friction.

## Missing Proof

- No side-project worktree or isolated directory exists yet.
- No side-project local report outbox exists yet.
- No side-project implementation attempt has been collected into the ledger
  yet.

## Next Action

Start SP1:

1. create an isolated `mew-companion-log` worktree or directory
2. define one bounded scaffold task
3. run the task mew-first
4. write a local report row in the side-project report outbox
5. let main Codex poll and append the accepted row to the main ledger

## Non-Goals

- do not implement the side project before SP0 is done
- do not treat Codex CLI implementation as mew-first autonomy credit
- do treat Codex CLI operating mew as `operator`, not `implementer`
- do not make GitHub issues for normal progress; create one `[side-pj]` issue
  only when mew cannot implement after bounded operator steering or a real
  problem needs main-side action
- do not change core mew unless the side project exposes a classified M6.14
  repair blocker or a later M6.16 measured hardening slice
- do not start GUI, Tauri, screen capture, TTS, or network-heavy side projects
  before the implementation-lane evidence cohort exists
