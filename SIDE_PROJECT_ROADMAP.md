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

## Second Project: mew-ghost

`mew-ghost` is the second side project when the user explicitly wants a larger
presence-oriented dogfood loop. It should stay isolated under
`experiments/mew-ghost` and exercise macOS-adjacent product work without editing
core mew.

Target shape:

- a small companion presence surface that can render beside editor/terminal work
- macOS active app/window-title detection through opt-in OS APIs
- graceful behavior when Accessibility permission is missing or the platform is
  not macOS
- a click/command contract that opens or prints `mew chat` / `mew code` launch
  intents without invoking resident loops during tests
- deterministic fixture tests for state mapping, macOS probe parsing, permission
  fallback, launcher contract, and generated local UI output

Non-goals for the first implementation arc:

- no screen capture, keystroke logging, or hidden background monitoring
- no live `.mew` state reads; use fixtures or explicit command output only
- no core `src/mew/**` imports or core command promotion
- no native app packaging until the fixture-tested shell and macOS probe
  contract are stable

### SP12: mew-ghost macOS Shell Scaffold

Create the isolated side project with a permission-safe macOS probe and a
deterministic visual shell.

Done when:

- `experiments/mew-ghost` has a README, Python entrypoint/modules, fixtures, and
  focused tests
- a command renders a local ghost state or HTML panel from a static fixture
- a macOS probe command reports the active app/window title when available and a
  structured permission/platform status when unavailable
- launcher actions produce explicit `mew chat` / `mew code` command intents
  without executing resident loops in tests
- the focused verifier is
  `UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`
- the attempt leaves a local side-dogfood report under
  `experiments/mew-ghost/.mew-dogfood/reports/`

### SP13: mew-ghost Live macOS Probe Integration

Connect the scaffold to an opt-in macOS active-window probe while keeping tests
hermetic.

Done when:

- the live probe uses an explicit command such as `--macos-probe`
- permission denied, missing `osascript`, timeout, and non-macOS cases are
  surfaced as user-readable structured states
- no probe runs unless the user invokes the probe command or opts into live mode
- tests cover every fallback path without requiring Accessibility permission

### SP14: mew-ghost Presence Loop

Make the ghost feel present while staying local and deterministic.

Done when:

- the ghost maps app/window/task state into visual states such as idle,
  attentive, coding, waiting, and blocked
- the local UI output refresh contract is documented
- fixture tests cover state transitions and stable rendered output

### SP15: mew-ghost Launcher Contract

Finish the side-project shell by defining safe launch behavior for mew actions.

Done when:

- `mew chat` and `mew code` intents are represented as explicit commands
- direct execution remains opt-in and outside tests
- README examples show safe dry-run and live macOS usage
- the side-project dogfood ledger summarizes the full mew-ghost arc and any
  reusable implementation-lane polish findings

### SP16: mew-ghost Watch Mode

Make the ghost useful as a continuously updating presence surface while keeping
the same permission and execution boundaries.

Done when:

- CLI watch mode can repeatedly print the current presence state until
  interrupted, with a bounded `--watch-count` path for tests
- HTML watch mode can repeatedly rewrite an output file for browser display,
  with the rendered page safely refreshing or otherwise showing fresh state
- watch mode keeps `--live-active-window` as the only live macOS probe opt-in
- watch mode never executes launcher commands unless `--execute-launchers` is
  also explicitly supplied
- tests cover bounded CLI watch output, bounded HTML output, interval handling,
  dry-run launcher safety, and no real `mew` subprocess execution
- README examples show safe CLI and HTML watch usage

### SP17: mew-ghost Desk Bridge

Connect the ghost shell to the core `mew desk --json` contract without making
the side project read live `.mew` state or import core mew.

Done when:

- a static desk-view-model fixture can be loaded by `mew-ghost`, for example
  with `--desk-json <path>`
- `mew desk` pet states such as `sleeping`, `thinking`, `typing`, and
  `alerting` map into ghost presence states without replacing the existing
  active-window classification path
- primary action data from the desk view model is rendered as an explicit,
  dry-run command intent alongside `mew chat` / `mew code`
- CLI state output and HTML output show the desk-derived status, counts, and
  primary action in a deterministic way
- watch mode can rebuild from the desk fixture on each bounded iteration
  without executing `mew desk --json`
- live command execution for `mew desk --json` remains deferred to a later
  explicit opt-in slice
- tests cover fixture loading, pet-state mapping, primary-action rendering,
  bounded watch rebuilds, and no live `.mew`/core import coupling
- README examples show safe desk-fixture usage
