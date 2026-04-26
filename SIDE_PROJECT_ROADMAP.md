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
- future state-oriented slices should use mew-state-like fixture JSON first;
  do not read live `.mew` state or edit core mew from the side-project lane

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

### SP6: Mew State Companion Export

Make the side project more valuable to mew's product story by rendering a
fixture-driven companion brief from mew-state-like data.

Done when:

- a static fixture represents mew-like local state, such as recent tasks,
  sessions, memory notes, dogfood rows, and open side-project issues
- a CLI mode such as `--mode state-brief` renders a concise companion markdown
  brief from that fixture
- the output names current state, recent work, unresolved risks, and next
  suggested side-project action without reading live `.mew` state
- README usage, stdout behavior, output-file behavior, and snapshot-style tests
  cover the new mode
- the attempt leaves a side-project dogfood ledger row with mew-first credit
  separated from Codex operator/reviewer work

### SP7: Multi-Fixture Companion Bundles

Let the side project combine several local fixture files into one deterministic
companion bundle.

Done when:

- a bundle fixture or manifest can point at multiple local session/state
  fixtures
- a CLI mode or option renders a combined companion markdown bundle without
  live network or live mew-state dependency
- ordering, grouping, and missing-fixture behavior are deterministic and
  covered by tests
- README examples show the bundle command and output-file path
- the attempt records whether mew kept closeout completeness without reviewer
  follow-up

### SP8: Multi-Day Companion Archive

Turn generated companion outputs into a small local archive/index model using
only fixture data and deterministic output paths.

Done when:

- fixture data can represent multiple days of companion outputs
- a CLI mode such as `--mode archive-index` renders an index grouped by day,
  surface, and next action
- no live filesystem crawl is required beyond explicit fixture paths supplied
  to the side-project CLI
- tests cover archive ordering, empty-day behavior, and stable markdown shape
- README documents how the archive index differs from the single-session brief

### SP9: Issue and Dogfood Ledger Digest

Make the side project summarize side-project implementation evidence in a
reader-friendly format, still from static fixtures.

Done when:

- fixture data can represent side-project dogfood rows and `[side-pj]` issue
  summaries without querying GitHub live
- a CLI mode such as `--mode dogfood-digest` renders outcomes, failure classes,
  rescue edits, and polish candidates
- the digest distinguishes product progress, blockers, and M6.16 polish input
- tests cover failure-class grouping and issue-link rendering
- any new reusable polish finding is raised as one `[side-pj]` issue rather
  than being hidden in chat

### SP10: Companion Export Contract

Define the stable local contract that would let a future core milestone consume
side-project output without coupling the side project to core mew.

Done when:

- the side project documents the input fixture schema and output markdown
  contract for report, journal, dream, research, state, bundle, archive, and
  dogfood surfaces
- schema examples stay local to `experiments/mew-companion-log`
- tests prove all documented modes still render and write output files
- no import from `src/mew/**` or live `.mew` state is introduced
- the contract names which future core milestone could adopt the surface and
  which decisions remain deferred

### SP11: Second Side-Project Gate

Decide whether `mew-companion-log` has produced enough evidence and product
clarity, or whether a second isolated side project would teach mew more.

Done when:

- the side-project dogfood ledger is summarized after SP6-SP10
- repeated failure classes, rescue edits, first-edit latency, and issue queue
  outcomes are compared against the first cohort
- the next recommendation is explicit: continue `mew-companion-log`, start a
  second side project, or pause side-project work for core M6.16/M9/M11 use
- if a second side project is recommended, it has a name, target shape,
  non-goals, focused verifier, and first milestone
- no implementation begins until the new roadmap/status entries are written
