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

## Second Project: mew-wisp

`mew-wisp` is the second side project when the user explicitly wants a larger
presence-oriented dogfood loop. SP12 through SP18 landed under the historical
`mew-ghost` codename and current `experiments/mew-ghost` implementation path.
From SP19 onward, the product name is `mew-wisp`: a terminal presence surface,
not a browser panel and not a fixed pet character.

The wisp is the resident CLI body that can later render different forms,
skins, or characters. Its name should survive if the displayed character
changes.

Target shape:

- a small terminal-first presence surface that can render beside editor or shell
  work
- a swappable display form layer, so the visible character can change without
  renaming the product
- macOS active app/window-title detection through opt-in OS APIs
- graceful behavior when Accessibility permission is missing or the platform is
  not macOS
- a click/command contract that opens or prints `mew chat` / `mew code` launch
  intents without invoking resident loops during tests
- deterministic fixture tests for state mapping, macOS probe parsing, permission
  fallback, launcher contract, and generated CLI/state output

Non-goals for the first implementation arc:

- no screen capture, keystroke logging, or hidden background monitoring
- no hidden live `.mew` state reads; keep machine-readable state/HTML on
  fixtures or explicit command output, while the user-facing human terminal path
  may use foreground repo-local live desk reads once covered by focused tests
  and an explicit fixture-terminal fallback
- no core `src/mew/**` imports or core command promotion
- no browser/HTML surface as the continuing product direction; SP19 should
  retire the earlier HTML proof path and keep terminal/state output
- no fixed pet identity; the wisp is a presence surface, while characters are
  replaceable forms
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

### SP18: mew-ghost Live Desk Opt-In

Let `mew-ghost` show real current mew desk state when the operator explicitly
opts in, while preserving fixture-only defaults and avoiding core imports.

Done when:

- default rendering still does not read live `.mew` state or run a desk command
- an explicit CLI flag such as `--live-desk` runs repo-local `./mew desk --json`
  without using a shell and with a short timeout
- live desk output is normalized through the same desk status/count/action
  surface used by the SP17 fixture bridge
- watch mode reruns the live desk command on each bounded/foreground iteration
  only when `--live-desk` is present
- failures such as missing command, nonzero exit, timeout, malformed JSON, and
  non-object JSON become structured desk states instead of crashing or retrying
  hidden work
- tests use injected runners/providers and do not spawn real `mew` subprocesses
- README examples show terminal and HTML watch commands for real desk state

### SP19: mew-wisp CLI-First Reset and HTML Removal

Rename the side-project direction from `mew-ghost` to `mew-wisp` and remove the
browser-oriented HTML proof path so the project converges on a terminal resident
presence.

Done when:

- README and side-project docs describe `mew-wisp` as the canonical product
  name, with `mew-ghost` kept only as historical codename/path context until a
  code-path rename lands
- `--format html`, HTML rendering helpers, HTML output tests, and HTML README
  examples are removed or replaced with terminal/state equivalents
- deterministic state/JSON output remains available for tests, dogfood reports,
  and future mew adapter integration
- the default human-facing render is terminal-first and does not require opening
  a browser or output file
- the first CLI wisp view can render from fixtures without live `.mew` reads,
  core imports, background monitoring, or launcher execution
- focused tests prove the CLI/state outputs and confirm no HTML mode remains
- the local dogfood report records the rename decision and HTML removal as a
  product convergence choice, not just cleanup

### SP20: mew-wisp Watch TUI Experience

Make the terminal wisp useful as a foreground resident view before adding more
live mew coupling.

Done when:

- watch mode updates the same terminal surface instead of requiring a browser
  refresh or dumping unreadable output
- bounded watch tests prove repeated updates, interval handling, and interrupt
  safety without real sleeps
- the CLI view makes state, current focus, and next dry-run action visible at a
  glance
- output remains calm enough for daily use in a terminal pane
- state/JSON output remains available separately for machine-readable proof

### SP21: mew-wisp Form Layer

Separate the terminal presence surface from the displayed character.

Done when:

- fixtures can select at least two forms, for example `default` and `cat`,
  without changing the underlying state model
- idle, coding, waiting, and blocked states map to form-specific expressions or
  poses through a small declarative layer
- tests prove that forms are interchangeable and do not change command
  execution, live-read, or launcher safety behavior
- README explains that the wisp is the surface/body and the character is a
  replaceable form

### SP22: mew-wisp Visual Polish

Make the fixture-first terminal surface feel like a resident wisp before adding
more mew coupling.

Done when:

- the default human view and cat form share a coherent visual theme rather than
  looking like debug logs
- the terminal output has a compact HUD, readable alignment, and a clear visual
  hierarchy for form, state, focus, signal, and next action
- state-specific form differences are visible but subtle enough for a terminal
  pane that stays open during work
- any color or ANSI styling degrades cleanly for plain output, tests, and
  non-TTY use
- focused tests cover theme selection, default/plain fallback, watch output,
  details output, and no regression to live-read or launcher execution behavior
- README examples show the polished terminal view and the escape hatch for
  diagnostic/plain output

### SP23: mew-wisp Speech Bubble

Make the CLI-first wisp appear to speak in text without adding audio or live
mew coupling.

Done when:

- normal `--format human` output includes a compact speech bubble between the
  visible form and the resident HUD panel
- utterances are deterministic and derived from fixture/state data such as
  presence state, focus/message, watch iteration, desk status, and primary
  action
- `idle`, `coding`, `waiting`, and `blocked` states produce distinct but short
  resident-facing lines
- the bubble centers and wraps with the same terminal-width behavior as the
  polished resident panel
- no TTS, audio playback, shell execution, hidden monitoring, live `.mew` reads,
  or core imports are introduced
- focused tests cover bubble placement, watch output, details gating, no
  regression to state/HTML/live/launcher behavior, and no audio/TTS flags

### SP24: mew-wisp Mew Adapter Reconnect

Reconnect the CLI-first wisp to real mew state after the terminal experience is
worth keeping on screen.

Done when:

- the same terminal view can render from fixture snapshots and explicit
  repo-local `./mew desk --json` output through one adapter boundary
- live mew reads remain opt-in and foreground-only
- adapter failures produce structured, visible fallback states
- tests use injected runners and fixture snapshots; a separate smoke proof may
  run the real `./mew desk --json` command from the repo root
- no internal mew state schema detail leaks into the form layer

### SP25: mew-wisp Human Watch Rerender

Make the terminal resident view behave like a live surface instead of an
append-only log when human watch mode is active.

Done when:

- `--format human` with `--watch` or `--watch-count` and no `--output` repaints
  the terminal surface in place
- state/HTML watch output and human `--output` behavior remain unchanged
- focused tests prove rerender controls are emitted for watched human output and
  are absent from JSONL/output-file modes
- no background monitoring, shell execution, launcher execution, hidden reads,
  or core imports are introduced

### SP26: mew-wisp Default Live Human Mode

Make the user-facing terminal resident connect to foreground repo-local mew
desk state by default, while keeping deterministic fixture display available
for tests and repeatable proof.

Done when:

- `--format human` and `--format human --form cat` use repo-local live desk
  state by default without requiring `--live-desk`
- an explicit fixture terminal flag preserves deterministic fixture display
- machine-readable state/HTML output keeps explicit `--live-desk` behavior
- focused tests cover default-live human/cat behavior, fixture fallback, README
  usage, and source isolation
- no background monitoring, launcher execution, hidden reads, shell execution,
  or core imports are introduced

### SP27: mew-wisp Readable Live Speech

Make the terminal speech bubble readable and honest about whether it is showing
fixture/local-terminal data or foreground live desk data.

Done when:

- the ASCII speech bubble has enough blank spacing to read naturally in a
  terminal pane
- fixture/demo output does not claim to be live mew state
- live human/cat output says it is live desk output and includes desk status or
  pet context when available
- focused tests prove fixture/local speech and live-desk speech stay distinct
- no background monitoring, launcher execution, shell execution, hidden reads,
  or core imports are introduced

### SP28: mew-wisp Stateful Resident Cues

Make the cat terminal form feel a little more alive across states while staying
deterministic and small.

Done when:

- the cat form exposes state-specific resident cues for idle, attentive,
  coding, waiting, and blocked states
- the cues are visible outside the cat silhouette so the reference mask stays
  stable
- centered, narrow-width, watch, live, fixture, and state/HTML behavior remain
  unchanged outside the intended human cat presentation
- focused tests cover the per-state cue table and existing layout invariants
- no live adapter coupling, background monitoring, launcher execution, shell
  execution, or core imports are introduced

### SP29: mew-wisp Live Work-Aware Speech Freshness

Make live terminal speech prefer the freshest foreground desk/work signal that
the adapter exposes, without adding hidden state reads or core coupling.

Done when:

- live desk speech prefers live desk detail/message/status text over fixture
  ghost focus/message copy
- fixture-terminal output remains deterministic and visibly fixture/local
- tests prove live-detail speech and fixture/local speech stay distinct
- real smoke output is inspected and any upstream desk freshness limitation is
  recorded as a separate implementation-lane issue
- no live adapter deepening, hidden monitoring, launcher execution, shell
  execution, broad refactors, or core imports are introduced

### SP30: mew-wisp Live HUD Coherence

Make the resident HUD agree with the live speech source in default live terminal
mode.

Done when:

- default live human/cat terminal output does not show fixture ghost
  focus/message in the HUD focus row when live desk detail/status/action is
  available
- fixture-terminal output keeps the deterministic fixture HUD
- watch layout, state output, HTML output, and existing live speech behavior
  remain covered by focused tests
- a real terminal smoke confirms live HUD focus and live speech point at the
  same live desk/work context
- no core imports, hidden monitoring, launcher execution, shell execution,
  broad refactors, or deeper live adapter coupling are introduced

### SP31: mew-wisp Compact Live Detail

Keep live terminal speech and HUD focus resident-sized even when the foreground
desk detail contains a long task instruction paragraph.

Done when:

- default live human/cat terminal output preserves the useful live desk/work
  signal without flooding the speech bubble or HUD focus row with full task
  instructions
- fixture-terminal output keeps deterministic fixture speech and HUD copy
- focused tests prove long live desk detail is compacted in both speech and HUD
  focus while the action line remains intact
- real live and fixture terminal smoke outputs are inspected
- no core imports, hidden monitoring, launcher execution, shell execution,
  broad refactors, or deeper live adapter coupling are introduced

### SP32: mew-wisp Launch Preset

Give the resident terminal experience a named launch preset so operators do not
need to remember the full human/cat/watch option stack.

Done when:

- a user-facing flag such as `--wisp` starts or represents the live human cat
  resident surface
- bounded `--watch-count` runs remain available for tests and demos
- explicit `--format`, `--form`, and fixture-terminal choices keep their
  existing behavior
- README usage documents the named preset
- focused tests cover the preset, explicit-option preservation, fixture mode,
  and existing state/html/launcher safety
- no core imports, hidden monitoring, launcher execution, shell execution, or
  broad refactors are introduced

### SP33: mew-wisp Product-Named Entrypoint

Move the user-facing Python entrypoint name toward `mew-wisp` while keeping the
historical `ghost.py` implementation module stable for compatibility.

Done when:

- a product-named local entrypoint such as `mew_wisp.py` delegates to the
  existing `ghost.py` main without duplicating CLI logic
- README usage prefers the product-named entrypoint while documenting that
  `ghost.py` is the historical implementation module
- focused tests prove the alias delegates to `ghost.main` and does not add
  shell execution, core imports, or duplicated argument parsing
- the product-named entrypoint can run the `--wisp` live and fixture terminal
  smoke paths
- no hidden monitoring, launcher execution, broad refactors, or core imports
  are introduced

### SP34: mew-wisp Resident-First Entrypoint Default

Make the product-named entrypoint feel like the resident CLI without requiring
operators to remember the historical `--wisp` flag.

Done when:

- invoking `mew_wisp.py` with omitted mode/form/watch intent and no `--output`
  starts the foreground human cat resident surface by default
- explicit `--format`, `--form`, `--watch`, `--watch-count`, and
  `--fixture-terminal` choices keep their existing behavior
- explicit `--output` preserves the historical HTML default for compatibility
- README usage documents the resident-first product entrypoint and the
  compatibility HTML output path
- focused tests cover the resident default, explicit output compatibility, and
  existing launcher/isolation safety constraints
- no hidden monitoring, launcher execution, shell execution, broad refactors,
  or core imports are introduced
