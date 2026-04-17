# Cockpit Reference Notes

Date: 2026-04-18

This note preserves the read-only `codex-ultra` investigations of:

- `/Users/mk/dev/tech_check/claude-code`
- `/Users/mk/dev/tech_check/codex`

The goal is not to copy either product. The goal is to extract cockpit lessons
that help mew become a passive resident AI shell that a model would want to
inhabit for task and coding work.

## Product Judgment

mew has become strong at reentry:

- passive ticks and runtime effects
- `desk`
- `journal`
- `mood`
- `morning-paper`
- `dream`
- `self-memory`
- `bundle --generate-core`

The next weakness is not memory. It is live work comfort.

An AI inside mew needs to know, every few seconds:

- what turn is active
- which tool is running
- whether progress is happening
- what command/test output matters
- what changed
- what approval or interrupt is blocking the loop
- how to resume without reconstructing state manually

The next implementation target should therefore be the coding cockpit, starting
with cell-based `mew work --follow` rendering.

## Claude Code Lessons

Reference paths from the investigation:

- `/Users/mk/dev/tech_check/claude-code/src/Tool.ts`
- `/Users/mk/dev/tech_check/claude-code/src/components/messages/AssistantToolUseMessage.tsx`
- `/Users/mk/dev/tech_check/claude-code/src/components/Messages.tsx`
- `/Users/mk/dev/tech_check/claude-code/src/components/VirtualMessageList.tsx`
- `/Users/mk/dev/tech_check/claude-code/src/components/shell/ShellProgressMessage.tsx`
- `/Users/mk/dev/tech_check/claude-code/src/tools/BashTool/BashToolResultMessage.tsx`
- `/Users/mk/dev/tech_check/claude-code/src/components/FileEditToolDiff.tsx`
- `/Users/mk/dev/tech_check/claude-code/src/components/permissions/PermissionRequest.tsx`
- `/Users/mk/dev/tech_check/claude-code/src/services/tools/StreamingToolExecutor.ts`
- `/Users/mk/dev/tech_check/claude-code/src/hooks/useCancelRequest.ts`
- `/Users/mk/dev/tech_check/claude-code/src/utils/sessionRestore.ts`

Key ideas:

- Tool rendering is a first-class contract, not generic JSON.
- Each tool owns its display name, summary, progress row, result renderer,
  search text, permission behavior, and interrupt behavior.
- The live transcript has stable rows. It groups and collapses noisy events
  instead of dumping raw logs.
- Long sessions need virtualization, offscreen freezing, search, and stable
  streaming rows.
- Command output should show live tail, elapsed time, line count, byte count,
  stdout/stderr separation, timeout state, and explicit empty output.
- Diff approval should snapshot the exact diff being approved.
- Approvals should be specialized by operation type: shell, file edit, web,
  MCP, plan, and so on.
- Abort should synthesize missing tool results so the session state remains
  complete.
- Background work should be a product primitive with status, output file,
  offsets, timestamps, and completion/failure notifications.
- Resume should restore working memory, not only chat text: cwd, file history,
  todos, context collapse data, mode/model metadata, and session pointers.

What mew should adapt:

- Tool display contracts for every native tool.
- Stable live rows for model turns and tool calls.
- Command/test renderer with compact preview plus detail.
- Approval cards by operation type.
- First-class foreground/background task records.
- Snapshot diff approvals after cell rendering exists.
- Semantic interrupt behavior after cell anchors exist.

## Codex CLI Lessons

Reference paths from the investigation:

- `/Users/mk/dev/tech_check/codex/codex-rs/app-server-protocol/src/protocol/common.rs`
- `/Users/mk/dev/tech_check/codex/codex-rs/app-server-protocol/src/protocol/v2.rs`
- `/Users/mk/dev/tech_check/codex/codex-rs/tui/src/history_cell.rs`
- `/Users/mk/dev/tech_check/codex/codex-rs/tui/src/exec_cell/model.rs`
- `/Users/mk/dev/tech_check/codex/codex-rs/tui/src/exec_cell/render.rs`
- `/Users/mk/dev/tech_check/codex/codex-rs/tui/src/diff_render.rs`
- `/Users/mk/dev/tech_check/codex/codex-rs/tui/src/bottom_pane/approval_overlay.rs`
- `/Users/mk/dev/tech_check/codex/codex-rs/tui/src/chatwidget.rs`
- `/Users/mk/dev/tech_check/codex/codex-rs/tui/src/bottom_pane/pending_input_preview.rs`
- `/Users/mk/dev/tech_check/codex/codex-rs/app-server/src/thread_state.rs`
- `/Users/mk/dev/tech_check/codex/codex-rs/app-server/src/command_exec.rs`

Key ideas:

- The app has typed thread, turn, item, approval, interrupt, and output-delta
  events.
- The transcript is cell-based, not log-line-based.
- Cells have compact display and richer transcript/detail rendering.
- Command cells normalize shell wrappers, syntax-highlight commands, classify
  read/list/search as exploration, and keep long output to head/tail previews.
- Tool calls are summarized semantically instead of shown as raw JSON.
- Diff rendering is first-class: file summaries, line counts, relative paths,
  gutters, syntax highlighting, hunk separators, wrapping, and large-diff
  limits.
- Approval UX uses one queue with scoped decisions: once, session, persistent
  prefix, host allow/block, permission grant, reject, or abort with steering.
- Interrupt and steer are distinct. User input while the agent is busy is either
  pending steer, queued follow-up, or immediate interrupt-and-submit.
- Resume reconnects to live state, including active turns and pending approvals.
- Standalone terminals are first-class objects with stdin, resize, terminate,
  deltas, timeouts, cwd/env/sandbox, and background summaries.

What mew should adapt:

- Cell-based transcript before deep TUI work.
- Compact preview with full detail nearby.
- Command/test cells with duration, status, output preview, and full output.
- Diff cells after command/test cells.
- One approval queue with scoped decisions.
- Pending steer and queued follow-up semantics after cells exist.
- Resume that includes live item state and pending approvals.
- Snapshot tests for cockpit regressions.

## Prioritized Mew Plan

### P0: Cell-Based `mew work --follow`

Initial implementation status, 2026-04-18:

- `src/mew/work_cells.py` builds stable cells over existing work-session state.
- `mew work --cells` and `/work-session cells` expose the cell view.
- `mew work --follow` prints newly added cells after each live step.
- The first dogfood pass showed that cell rows should prioritize preview text
  over raw ids and timestamps; the formatter now keeps ids/timing as metadata
  lines under each row.

Estimated time: 1 to 1.5 focused days.

Why first:

- Existing work sessions already have structured model turns and tool calls.
- The main pain is that useful structure is flattened into text.
- Approval, interrupt, diff, and resume-live-state all need stable cells to
  point at.

Strict first slice:

- Add a small cell builder over existing work session state.
- Cell kinds:
  - `model_turn`
  - `tool_call`
  - `command`
  - `test`
  - `diff`
  - `approval`
- Minimum fields:
  - stable `id`
  - `kind`
  - `status`
  - `started_at`
  - `finished_at`
  - one-line `preview`
  - optional `detail`
  - optional tail buffer for command/test output
- `mew work --follow` should render cells in order.
- TTY mode can later redraw active cells in place.
- Non-TTY mode should still emit stable, readable cell lines.

Do not include in the first slice:

- full TUI
- diff approval workflow
- approval queue redesign
- interrupt/steer semantics
- live resume of pending approvals

### P1: Command/Test Renderer

Initial implementation status, 2026-04-18:

- Command/test cells include command, cwd, exit status, elapsed time,
  stdout/stderr line and character counts, output tails, explicit no-output
  rows, timeout/error metadata, and a `full_output` hint back to the focused
  pane.
- The remaining work is pacing and control: configurable tails, collapse/expand,
  and a cleaner cell-native follow stream.

Estimated time: 0.5 to 1 day after P0.

Show:

- command
- cwd
- elapsed time
- status
- exit code
- stdout/stderr split or tagged merged tail
- timeout marker
- explicit `(no output)`
- full output reference when available

### P1: Approval Anchors

Estimated time: 1 day after cells exist.

Add operation-specific approval cells for:

- file writes
- shell commands
- network
- agent runs

The first useful version only needs:

- approve once
- reject
- reject with feedback
- show exact target/path/command

### P1: Interrupt/Steer Semantics

Estimated time: 1 to 2 days after cells exist.

Rules to make explicit:

- user message becomes pending steer
- user message becomes queued follow-up
- user message interrupts current turn and submits immediately

The UI must show which route was chosen. Nothing should be silently dropped or
surprisingly sent.

### P2: Diff Cells

Estimated time: 1 day.

Show:

- files changed
- lines added/deleted
- compact hunks
- full diff detail path or command

### P2: Resume Live State

Estimated time: 2 to 3 days.

Resume should restore:

- active model turn
- active tool cells
- pending approvals
- last command/test tail
- cwd/worktree
- permissions
- queued user input

## Next Recommended Task

Continue from the landed P0 slice and the first command/test-cell polish into
approval anchors:

> Add operation-specific approval cells that point at exact write/shell/network
> targets and support approve once / reject / reject with feedback.

Target duration:

- first useful slice: 4 to 6 hours
- polished dogfooded slice: 1 to 1.5 days

Done when:

- a live or resumed work session can be read as stable cells
- command/test/tool/model activity is visible without reading raw state JSON
- old work remains compact
- active work has an obvious current cell
- tests cover rendering from recorded work session fixtures
