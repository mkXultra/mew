# Claude Code Loop Patterns For Mew Stabilization

## Executive Summary

Claude Code’s highest-value stabilization pattern is structural, not prompt-level: exploration, task progression, and tool execution are separate runtime objects with explicit invariants.

Mew already has useful substrate in `src/mew/work_session.py`, `src/mew/work_loop.py`, and `src/mew/toolbox.py`: cached read windows, write-ready detection, dry-run/apply/verify gating, running command output, continuity scoring, and timeout diagnostics. The current gap is that these remain mostly prompt-managed rather than executor-managed.

That gap maps directly to the two failure buckets:

| Failure bucket | What mew has today | Missing pattern from Claude Code |
| --- | --- | --- |
| Exact cached windows exist but no safe dry-run patch is produced | `plan_item_observations`, `target_path_cached_window_observations`, `build_write_ready_work_model_context()` and a narrowed write-ready prompt in `src/mew/work_loop.py` | A first-class current task/todo item that explicitly owns the next draft step and its cached-window refs, so the loop advances a persisted step instead of re-deriving intent from prompt history |
| Exploration completes but the next draft step times out | Rich resume/context in `build_work_session_resume()` plus a 90s write-ready think timeout in `src/mew/work_loop.py` | A thinner handoff between explore and draft, and an executor that treats reads, writes, and interruptions as lifecycle events rather than one sequential batch plus another full model turn |

The patterns to adopt now are:

1. A hard read-only explore mode with a narrow tool surface and explicit handoff output.
2. A session-scoped todo/task ledger that survives resume and owns exactly one in-progress next step.
3. A streaming executor state machine with fail-closed concurrency defaults, ordered result emission, and synthetic terminal states on abort/fallback.

One important conclusion: mew does **not** mainly need more prompt instructions here. It needs more runtime state.

## Relevant Reference Files

Reference files actually worth copying from:

- `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/exploreAgent.ts`
  Hard read-only exploration contract. The explore agent removes edit/write tools entirely and narrows Bash to read-only operations.
- `references/fresh-cli/claude-code/src/utils/messages.ts`
  Plan mode forces an explore-only first phase and explicitly encourages parallel explore agents before planning/editing.
- `references/fresh-cli/claude-code/src/tools/TodoWriteTool/TodoWriteTool.ts`
  Session task list is a real tool-backed state mutation, not only model prose.
- `references/fresh-cli/claude-code/src/tools/TodoWriteTool/prompt.ts`
  Strong task invariants: create todos early, exactly one `in_progress`, update immediately, do not mark complete when blocked.
- `references/fresh-cli/claude-code/src/utils/sessionRestore.ts`
  Restores todo state from transcript so resume does not depend on re-planning.
- `references/fresh-cli/claude-code/src/tasks/RemoteAgentTask/RemoteAgentTask.tsx`
  Pulls the last todo list back out of remote-agent logs, so subagent work also keeps a recoverable task frontier.
- `references/fresh-cli/claude-code/src/Tool.ts`
  Safe defaults matter: `isConcurrencySafe=false` and `isReadOnly=false` unless a tool proves otherwise.
- `references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts`
  Core executor lifecycle: `queued -> executing -> completed -> yielded`, per-tool abort controllers, ordered result yield, selective sibling cancellation, progress streaming.
- `references/fresh-cli/claude-code/src/services/tools/toolOrchestration.ts`
  Partitions safe concurrent batches from serial batches and applies context modifiers only where safe.
- `references/fresh-cli/claude-code/src/services/tools/toolExecution.ts`
  Guarantees tool results become transcript messages and keeps context modification separate from message emission.
- `references/fresh-cli/claude-code/src/query.ts`
  Important invariant handling around streaming fallback and user interrupts: orphaned tool state is discarded/tombstoned and remaining terminal results are still emitted.

Mew comparison files used for contrast:

- `src/mew/work_loop.py`
- `src/mew/work_session.py`
- `src/mew/commands.py`
- `src/mew/runtime.py`
- `src/mew/toolbox.py`
- `src/mew/tasks.py`
- `tests/test_work_session.py`
- `tests/test_toolbox.py`

Note: this Claude Code checkout did not expose dedicated unit tests for these exact reference files. The test-design recommendations below are extracted from the runtime invariants in the implementation.

## Design Patterns To Adopt Now

### 1. Add a real read-only explorer boundary

Copy the separation, not the whole subagent stack.

Claude Code pattern:

- `exploreAgent.ts` enforces read-only behavior by tool surface, not by polite instruction alone.
- `utils/messages.ts` makes exploration a distinct phase before planning/editing.

Why it matters for mew:

- In mew, `build_work_think_prompt()` mixes exploration, planning, and draft selection in one model turn.
- That allows the loop to keep rediscovering or rereading even when the real next step should be “draft from known windows.”

Adopt in mew:

- Add an explicit `explore` work mode or action family that only permits `inspect_dir`, `search_text`, `glob`, `read_file`, `git_status`, `git_diff`, and `git_log`.
- Its output should be structured, small, and reusable:
  - `target_paths`
  - `cached_window_refs`
  - `candidate_edit_paths`
  - `exact_blockers`
- Do not let explore emit write tools, `run_tests`, or `run_command`.

Best mew landing zone:

- `src/mew/work_loop.py`
- `src/mew/work_session.py`

### 2. Replace prompt-only plan memory with a session todo ledger

Claude Code pattern:

- `TodoWriteTool` turns decomposition into runtime state.
- `sessionRestore.ts` and `RemoteAgentTask.tsx` restore it from transcript/logs.

Why it matters for mew:

- Mew’s current short-horizon plan lives in `working_memory.plan_items`, recovered from prior model turns by `build_working_memory()` in `src/mew/work_session.py`.
- That is useful, but it is still derived state from model output, not an independently mutable current-task ledger.
- When exact cached windows already exist, the loop still has to infer which plan item is “now drafting the patch” instead of advancing a persisted in-progress item.

Adopt in mew:

- Add session-scoped work todos under the work session itself, separate from global `tasks.py`.
- Minimum fields:
  - `id`
  - `content`
  - `active_form`
  - `status` (`pending|in_progress|blocked|completed`)
  - `target_paths`
  - `cached_window_refs`
  - `verify_command`
  - `blocker`
- Keep exactly one `in_progress`.
- Write/update this state before and after each important loop boundary:
  - after exploration finishes
  - before draft generation
  - after dry-run preview succeeds
  - after approval/apply/verify

Best mew landing zone:

- `src/mew/work_session.py`
- `src/mew/commands.py`
- `tests/test_work_session.py`

### 3. Bind cached windows to the current todo, not only to resume prose

Claude Code pattern:

- Task state and executor state are explicit enough that the next step can consume prior structured outputs directly.

Why it matters for mew:

- Mew already has the right raw ingredients:
  - `plan_item_observations`
  - `target_path_cached_window_observations`
  - `recent_read_file_windows`
  - `build_write_ready_work_model_context()`
- The missing piece is ownership. Those cached windows are not attached to a durable current draft item.

Adopt in mew:

- When `plan_item_observations[0].edit_ready` becomes true, create or update the current todo with exact cached-window refs.
- The next draft step should take only:
  - current todo
  - cached window text
  - write policy
  - verifier hint
- If the draft step cannot proceed, it must return one exact blocker tied to one referenced window, not a fresh broad search.

This is the most direct fix for “exact cached windows exist but no safe dry-run patch is produced.”

### 4. Introduce executor lifecycle states, not just running/completed/failed

Claude Code pattern:

- `StreamingToolExecutor.ts` tracks `queued`, `executing`, `completed`, and `yielded`.
- `Tool.ts` defaults every new tool to non-concurrent until proven safe.
- `toolOrchestration.ts` batches concurrent-safe reads separately from serial tools.

Why it matters for mew:

- `start_work_tool_call()` in `src/mew/work_session.py` only gives mew `running`, then `finish_work_tool_call()` makes it `completed` or `failed`.
- Batch execution in `src/mew/commands.py` is sequential and stop-on-first-error.
- There is no queued/yielded layer, no ordered concurrent read execution, and no executor-owned interruption semantics.

Adopt in mew:

- Add executor states:
  - `queued`
  - `executing`
  - `completed`
  - `cancelled`
  - `yielded`
- Mark tools concurrency-safe only when explicitly proven:
  - start with `read_file`, `search_text`, `glob`, `inspect_dir`, `git_status`, `git_diff`, `git_log`
  - keep writes and verification serial
- Preserve output order even if concurrent-safe reads finish out of order.

This is the most direct fix for “exploration completes but the next draft step times out,” because it shortens and stabilizes the explore half before the draft call even starts.

### 5. Copy selective sibling cancellation, not blanket cancellation

Claude Code pattern:

- In `StreamingToolExecutor.ts`, a Bash failure aborts sibling subprocesses, but independent read/web failures do not nuke the whole batch.

Why it matters for mew:

- Current mew batch behavior in `src/mew/commands.py` halts on first error and invalidates pending approvals after sibling failure.
- That is reasonable for write batches, but too coarse for read-heavy exploration.

Adopt in mew:

- Use different cancellation domains:
  - concurrent read batch: one read failure does not cancel sibling reads
  - shell/verify batch: failure may cancel siblings
  - write batch: stop immediately and mark later siblings as not-run/cancelled

### 6. Guarantee terminal tool records on interrupt, timeout, and fallback

Claude Code pattern:

- `query.ts` drains remaining executor results on abort.
- Streaming fallback discards orphaned state and emits terminal cleanup rather than leaving half-open tool calls.

Why it matters for mew:

- Mew already has timeout diagnostics in `src/mew/toolbox.py` and hard model timeout handling in `src/mew/work_loop.py`.
- What it still lacks is a tool-level invariant that every started tool call reaches a terminal replayable state, even when the surrounding model turn or batch is interrupted.

Adopt in mew:

- On batch abort/repair/runtime interruption, mark untouched siblings as `cancelled` or `not_run`.
- Never leave “running” tool calls as the only explanation for a stalled turn.
- Make resume logic consume those terminal states instead of reconstructing intent heuristically.

## Test/Replay Harness Ideas For Mew

### 1. Cached-window-to-draft replay

Fixture:

- Work session with:
  - one current todo in `in_progress`
  - exact source/test cached windows
  - no pending approvals

Assertions:

- The next planner call emits a paired dry-run batch or one exact blocker.
- It does not emit `search_text` or broad `read_file`.

Best target:

- `tests/test_work_session.py`

### 2. Explore-to-draft handoff replay

Fixture:

- One explore step populates `target_paths` and cached window refs.
- A second step starts from only that state.

Assertions:

- Explore step cannot schedule writes.
- Draft step consumes the cached refs directly and skips rediscovery.

Best target:

- `tests/test_work_session.py`

### 3. Executor concurrency invariant test

Fixture:

- Synthetic batch containing:
  - two concurrency-safe read tools
  - one serial write or verification tool
  - one more read tool after the serial tool

Assertions:

- Initial reads may overlap.
- Serial tool waits until prior reads settle.
- Later read waits until serial tool finishes.
- Yield order matches submission order.

Best target:

- new `tests/test_work_executor.py`

### 4. Interrupt/fallback completion test

Fixture:

- Start a multi-tool batch, then interrupt after one tool has started and another is still queued.

Assertions:

- Started tool gets a terminal state.
- Queued tool becomes `cancelled`/`not_run`.
- Resume does not see stale `running` calls.

Best target:

- `tests/test_runtime.py`
- `tests/test_work_session.py`

### 5. Draft-timeout recovery test

Fixture:

- Current todo is “draft paired dry-run edit.”
- Cached windows already attached.
- First draft call times out.

Assertions:

- Reentry keeps the same todo as current.
- Prompt context for retry is smaller than the original full resume path.
- Retry starts from draft, not from exploration.

Best target:

- `tests/test_work_session.py`

### 6. Prompt-budget regression test

Measure:

- chars for:
  - full work context
  - explore handoff
  - current-todo draft prompt

Assertion:

- edit-ready draft prompt remains below a fixed budget and below the generic resume prompt.

Best target:

- `tests/test_work_session.py`

## What Not To Copy

- Do not copy Claude Code’s full coordinator/subagent product surface. The useful part is the boundary, not the UI or agent marketplace.
- Do not copy the entire hook, MCP, permission, or telemetry stack. Mew needs executor invariants first.
- Do not copy deferred-tool discovery (`shouldDefer`, ToolSearch) unless mew later has too many tools for the model to reliably see.
- Do not copy concurrency assumptions blindly. Keep mew fail-closed like `Tool.ts`: new tools should default to non-concurrent until proven safe.
- Do not copy transcript tombstones literally unless mew adopts streaming assistant-message replacement. Copy the invariant instead: every interrupted tool sequence must still be structurally recoverable.

## Proposed Next Tasks For Mew

1. Add session-scoped `work_todos` with exactly one `in_progress` item and attach cached-window refs to it.
2. Add an explicit read-only explore action family in `src/mew/work_loop.py` and refuse writes from that phase.
3. Add a current-todo draft fast path that takes only the todo, cached window texts, write policy, and verifier hint.
4. Introduce a small work executor module with queued/executing/completed/cancelled/yielded states and concurrency-safe read batches.
5. Move mew batch execution in `src/mew/commands.py` behind that executor instead of open-coding sequential loop control.
6. Add replay tests for:
   - cached-window-to-draft
   - draft-timeout-to-direct-retry
   - interrupt/fallback terminal-state completion
