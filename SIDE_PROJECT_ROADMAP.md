# Mew Side Project Implementation Roadmap

This roadmap is for isolated side projects that mew builds to exercise and
measure its implementation lane. It is separate from the core roadmap: side
projects should generate evidence for core M6.16 without destabilizing mew's
runtime, memory, or work-loop substrate.

## Operating Contract

- Side project implementation is mew-first by default.
- This lane is implementation dogfood: mew should do the bounded product work,
  while the reviewer records enough telemetry to improve mew's implementation
  lane later.
- Side-project Codex CLI normally acts as `operator`: it runs mew from the
  side-project directory, makes local decisions, and supervises the attempt.
- Codex or Codex CLI may also act as `reviewer`, `comparator`, or `verifier`.
  If it writes the product patch directly, record it as `fallback` or
  `implementer`.
- Every completed bounded implementation attempt should leave one structured
  local report in the side-project report outbox. Main Codex polls those
  reports and appends accepted rows to
  `proof-artifacts/side_project_dogfood_ledger.jsonl` using
  `mew side-dogfood append`.
- GitHub issues are only for problems. Use one problem per issue, add the
  `[side-pj]` title prefix, and rely on open/closed state; do not add a label
  workflow until it is proven necessary.
- Reply/chat logs are auxiliary evidence. The side-project dogfood ledger is
  the primary evidence for M6.16 implementation-lane polish.
- Keep side-project code isolated in a separate worktree or directory. Do not
  edit core mew unless the side project exposes a classified implementation-lane
  blocker that belongs in M6.14 or a measured hardening slice for M6.16.

## First Project: mew-companion-log

`mew-companion-log` is the first recommended side project because it is
medium-sized, local-first, easy to test, and close to the passive-AI product
story without requiring GUI, OS permissions, or network access.

Target shape:

- a small CLI or package that generates companion markdown from local JSON
  fixtures
- journal, dream, and summary surfaces that can later connect to mew state
- deterministic fixture tests and proof artifacts
- no dependency on Tauri, screen capture, TTS, or external SaaS for the first
  dogfood loop

## Milestones

### SP0: Dogfood Harness Ready

Prepare enough structure that a side-project task can start without losing the
evidence needed by M6.16.

Done when:

- `SIDE_PROJECT_ROADMAP.md` exists and names the first side project
- `SIDE_PROJECT_ROADMAP_STATUS.md` states the active side-project focus
- `.codex/skills/side-pj-mew-impl/SKILL.md` tells future agents how to run and
  record side-project implementation dogfood attempts
- `mew side-dogfood template`, `append`, and `report` are the canonical ledger
  interface
- the first side-project task can be started in a separate worktree or isolated
  directory with a clear local-report and problem-issue plan

### SP1: mew-companion-log Scaffold

Create the side project with a minimal runnable shape.

Done when:

- an isolated worktree or directory exists for `mew-companion-log`
- the project has a README, CLI entrypoint or script, and fixture directory
- one command can read a fixture JSON and write or print a markdown companion
  report
- tests cover the first command
- the attempt leaves a local report that main Codex can append to the
  side-project dogfood ledger

### SP2: Journal and Dream Reports

Make the side project useful as passive-AI companion output.

Done when:

- fixture-driven morning journal output exists
- fixture-driven evening journal output exists
- fixture-driven dream/learning output exists
- generated markdown is stable enough for snapshot-style tests
- at least two bounded mew-first implementation attempts are recorded, with
  Codex CLI roles separated from mew autonomy credit

### SP3: Implementation-Lane Evidence Cohort

Use the side project to measure whether mew can implement ordinary bounded
coding tasks.

Done when:

- at least five side-project dogfood attempts are recorded
- each row has task/session id, Codex CLI role, verifier status, rescue edits,
  outcome, failure class, proof artifacts, and commit where applicable
- failures are classified instead of silently rescued
- any structural mew-first failure is routed to M6.14 repair or explicitly
  deferred with rationale

### SP4: Optional Research Digest Slice

Only after SP1-SP3 provide useful implementation-lane evidence, add a small
static-feed research digest if it still helps product learning.

Done when:

- static fixture feed ranking exists
- no live network dependency is required
- the added scope improves dogfood evidence or product clarity

### SP5: Feed M6.16

Turn side-project evidence into implementation-lane hardening work.

Done when:

- the side-project dogfood ledger is summarized for M6.16
- the main failure classes, rescue points, and first-edit latency are named
- the next core hardening slice is chosen from measured evidence rather than
  subjective impressions
