# Mew Roadmap Status

Last updated: 2026-04-17

This file tracks progress against `ROADMAP.md`. Keep it evidence-based and conservative.

## Summary

| Milestone | Status | Short Assessment |
|---|---|---|
| 1. Native Hands | `done` | `mew work --ai` can inspect, edit, verify, resume, and expose an audit trail without delegating to an external coding agent. |
| 2. Interactive Parity | `in_progress` | `mew work --ai` now has deterministic live steps, command/model streaming with readable compact model deltas, phase/elapsed progress anchors, grouped action/result panes, compact chat controls, work-mode/follow cockpit controls, interrupt/max-step reentry notes, approval/live controls, chat transcript logging, and work-session/global ledgers; the remaining gap is a polished continuous REPL-style coding cockpit. |
| 3. Persistent Advantage | `in_progress` | Task-local resume, working memory, durable work notes, older-tool digests, live world-state context, and task-kind scoped reentry views now exist; day-scale reentry and passive watcher advantage are not yet proven. |
| 4. True Recovery | `foundation` | `doctor`, `repair`, runtime effect journal, `recovery_hint`, and `outcome` exist; automatic safe resume is not implemented. |
| 5. Self-Improving Mew | `foundation` | Native self-improvement dogfood can produce useful implementation targets and preserve recent completed work, but closed-loop self-improvement is not yet reliable. |

## Current Focus

Milestone 2 is the active focus. Already shipped: readable diff panes,
command/test output panes, chat work-mode, bounded follow loops, compact live
result panes, readable compact model-delta previews, phase/elapsed progress
anchors, chat transcript logging, interrupt/max-step reentry notes, and scoped
reentry controls. Remaining gap: a calmer continuous coding cockpit with a more
stable reasoning/status pane, less repeated reentry material during long
sessions, and more real dogfood on repository work.

## Milestone 1: Native Hands

Status: `done`

Evidence:

- Native read/write/verify helper modules exist.
- Runtime action application can perform bounded actions.
- `src/mew/action_application.py` started extracting action application helpers.
- Roadmap first slice is defined.
- `work_session` state now tracks active native work sessions and their tool calls.
- `mew work <task-id> --start-session` starts or reuses a native work session.
- `mew work --tool read_file|search_text|glob|inspect_dir --allow-read ...` runs read-only native tools and journals outcomes.
- `mew work --tool run_tests --allow-verify ...` runs verification commands and journals command results.
- `mew work --tool run_command --allow-shell ...` runs explicitly gated shell commands and journals command results.
- `mew work --tool write_file|edit_file --allow-write ...` previews writes by default.
- Applied `write_file`/`edit_file` requires `--allow-verify` and `--verify-command`; failed verification rolls the write back and records the failed tool result.
- `mew work <task-id> --ai` calls the resident model in THINK/ACT phases, records `model_turns`, executes one selected work-session tool per step, and feeds prior tool results into the next model prompt.
- Unit coverage proves a model-selected `read_file` is journaled and that the second model turn can see the first tool result.
- Unit coverage proves `mew work --ai` reuses an existing active session across separate invocations and can resume with prior tool output.
- Live Codex Web API dogfood in a temporary workspace fixed `calc.add`: read `calc.py`, applied an `edit_file` changing subtraction to addition, ran the configured verification command with exit code 0, then finished.
- `/work-session` in chat can start, show, and close native work sessions.
- `dogfood --scenario work-session` exercises session creation, `read_file`, `glob`, `run_tests`, dry-run `edit_file`, verified `write_file`, and workbench journal visibility.

Missing proof:

- Larger real-world coding tasks may still expose UX and context limits, but the Milestone 1 done criteria are satisfied.

Next action:

- Historical handoff complete. Keep current implementation work under Milestone 2's active focus rather than reopening Milestone 1.

## Milestone 2: Interactive Parity

Status: `in_progress`

Evidence:

- `mew chat` exists.
- Chat can inspect focus, status, workbench, agents, verification, writes, thoughts, runtime effects, doctor, and repair.
- `mew work --session --details` and `/work-session details` expose touched files, model turns, and tool-call summaries for the active work session.
- `mew work --session --diffs` and `/work-session diffs` expose a focused cockpit diff pane for recent write/edit previews and applied writes.
- `mew work --session --tests` and `/work-session tests` expose a focused cockpit test/verification pane for recent run output.
- `mew work --session --commands` and `/work-session commands` expose a focused cockpit command-output pane for recent command stdout/stderr.
- Compact resume bundles now include clipped stdout/stderr previews for recent commands, so live/reentry output can show key test or shell output without switching panes.
- Truncated command output previews now start on a line boundary, avoiding confusing partial-line fragments in the cockpit.
- `mew work --session --timeline` and `/work-session timeline` show a compact chronological model/tool event timeline for cockpit reorientation.
- `mew work --ai` streams progress events to stderr in normal mode, and with `--progress` when JSON output is requested.
- Work-session details now include a `Recent diffs` section for write/edit tool calls, including verification exit code and rollback state.
- Pending write approvals in resume output and inline `--prompt-approval` now include clipped diff previews with added/removed line counts, so the cockpit can support approve/reject decisions without opening a separate details view.
- Dry-run `write_file`/`edit_file` tool calls can be explicitly applied with `mew work --approve-tool ...` or rejected with `mew work --reject-tool ...`.
- `/work-session approve <tool-call-id> --allow-write ... --verify-command ...` and `/work-session reject <tool-call-id> ...` expose the same approval flow inside chat.
- `run_tests` tool calls now fail the work-session step when the verifier exits nonzero, and `/work-session details` includes a compact `Verification failures` section with command, cwd, exit code, stderr, and stdout context.
- `--progress` streams `run_tests`, `run_command`, and write-verification stdout/stderr lines to stderr for both manual work tools and `mew work --ai`.
- `/work-session ai ...` lets the user run a resident model work step from inside `mew chat`, using the same gates as `mew work --ai`.
- `dogfood --scenario work-session` now exercises chat `/work-session details` and `/work-session resume --allow-read .`, so cockpit visibility and live world-state resume are part of the recurring dogfood path.
- Native work reads now default to 50,000 characters, while model work-session context clips recent `read_file` text to a smaller page with `visible_chars`, `source_text_chars`, and a resume `next_offset`, reducing long-session prompt growth without losing the path to request more file content.
- Work sessions now expose read-only `git_status`, `git_diff`, and `git_log` tools behind the read gate, avoiding unnecessary `--allow-shell` for common coding context.
- `mew work --ai --act-mode deterministic` can skip the second model ACT call and normalize THINK output locally; the default remains model ACT to preserve the original THINK/ACT architecture.
- `mew work --session --resume` and `/work-session resume` produce a compact reentry bundle with touched files, commands, failures, pending approvals, recent decisions, and next action.
- The same resume bundle is included in work-mode model context so the resident model sees reentry state without reconstructing it from raw tool history.
- Work-session resume bundles now include compact `working_memory` when available, giving humans and future model turns a short hypothesis, next step, open questions, and latest verification state.
- Work-session working memory now also surfaces the latest tool observation and marks itself stale when a tool result landed after the memory was written; human-facing resumes label old plans as `stale_next_step`, preventing pre-tool `next_step` text from looking current after a live step.
- `mew work --session --resume --allow-read ...` and `/work-session resume --allow-read ...` add live git status and touched-file stats to the resume, and before any file is touched they show a shallow allowed-root snapshot for non-git workspaces. The same bounded world-state summary is injected into future work-model context when read access is allowed.
- Resume world-state git status now probes allowed read roots before falling back to the current directory, so reentry from a disposable cwd can still report the actual project repo state.
- `mew work --live` runs the resident work loop with progress and prints a resume bundle after each completed tool step.
- `mew archive` now archives closed work sessions, which gives large work-session histories a retention path after read/context limits increased.
- `read_file` supports `offset` and returns `next_offset`, letting the resident model page through files larger than one read window.
- Codex Web API SSE text deltas are forwarded even when the response omits a `content-type` header; `--follow` enables batched live `model_delta` thinking-pane output by default when the backend supports it.
- Compact follow mode suppresses duplicate stderr delta progress while still preserving the model stream in the thinking pane and final preview, reducing token-by-token noise during real Codex Web API dogfood.
- Compact follow mode now suppresses the duplicate raw `stream_preview` when live model deltas were already shown, keeping the planning summary to model-stream metrics, summary, action, and reason.
- Compact follow mode now renders plan-shaped JSON streams as readable `model_summary_delta`, `model_reason_delta`, and `model_action_delta` lines instead of raw JSON tokens.
- `mew work --live` now prints a compact `thinking` pane before each action, showing the model summary and planned action before any tool runs.
- Live thinking panes now include a stable progress anchor (`step/max`, session id, task id, phase, and elapsed time), improving orientation during multi-step resident work.
- `mew work --live --compact-live` and `/work-session live --compact-live` skip full per-step resume blocks, leaving a lighter thinking/action/result stream for longer supervised runs.
- Compact live mode also keeps the final step report to command/cwd/exit summaries, avoiding stdout/stderr replay after the result pane.
- `mew work --live` now prints a compact `result` pane after each step, combining tool outcome, command output, phase, context pressure, pending approvals, and next action before the full resume block.
- Live result panes now surface compact work-session memory (`memory_hypothesis`, `memory_next`/`stale_memory_next`, and verification state), so compact follow keeps the resident model's current belief and next intended step visible without opening a full resume.
- Live result, resume, and workbench reentry panes now include a recurring-failure ribbon when the same tool/target/error repeats, making loops visible before the resident blindly retries the same broken action again.
- Live result panes now group `outcome`, `tools`, and `session`, include per-tool duration when timestamps are available, indent multiline command metadata consistently, and place command cwd/stdout/stderr directly under the tool result instead of a duplicate `summary: command` line.
- Live result panes suppress duplicate step/tool summaries, keeping command and tool outcomes easier to scan during dogfood.
- Live result panes now use compact read/search/glob summaries instead of dumping file text into the main cockpit stream.
- Live result panes now show bounded `search_text` context snippets around matches, so compact runs reveal what the resident model found without opening full session details or forcing conclusions from a single matched line.
- Final `mew work --ai` step reports now reuse compact tool summaries, so live runs do not reprint read-file bodies after the resume.
- `mew work --live` now prints the selected action, reason, key parameters, and tool-call id before execution, so the user can see what the resident model is about to do before the resume bundle appears.
- `/work-session live ...` provides a chat shortcut for the same live resident work loop, and pending write approvals in resume output include concrete `/work-session approve ...` and `/work-session reject ...` hints.
- Interactive `mew work --live` and `mew do` prompt inline by default for dry-run writes, with clipped diff preview, the approval verification command, `--prompt-approval` for non-TTY forcing, and `--no-prompt-approval` for explicit opt-out.
- `/work-session live` inherits the same interactive inline approval behavior from chat, and focused work help now documents the default plus `--no-prompt-approval`.
- Work-session resume output now reports context pressure (`tool_calls`, `model_turns`, recent chars, total chars, pressure), making large active-session growth visible to both humans and the model.
- A real Codex Web API dogfood run on task #21 used `mew work --live --act-mode deterministic` for two read-only steps; it selected `inspect_dir` then `read_file`, printed action/reason/resume/context pressure for each step, and made no repository writes.
- Work-mode control actions now have side effects: `send_message` writes to outbox, `ask_user` creates a normal question, and `finish` closes the work session while appending a final note to the task.
- Work-mode `finish` can now explicitly set `task_done: true` with a completion summary, separating "close this work session" from "mark the task done".
- Closed work sessions can still be inspected with `mew work <task-id> --session --resume`, so a finished resident work loop leaves a durable reentry/final-state artifact.
- `mew chat` now has `/continue ...` as a short one-step live command for the active work session, reducing the repeated `/work-session live ...` command burden.
- Work mode now supports a read-only `batch` action with up to five inspection tools in one model turn, journaling each tool call separately while keeping writes and shell commands outside batch mode.
- `glob` now skips common generated/cache directories such as `.git`, `.pytest_cache`, `.venv`, `__pycache__`, and `node_modules`, reducing noisy read-only navigation for resident models.
- Codex Web API dogfood for batch exposed a missing `read_file.path` failure, after which batch normalization was hardened to skip invalid read subtools; retrying the same dogfood task completed `inspect_dir` and `read_file README.md` in one model turn without writes.
- Work-session resume next-action selection now keys off the latest tool result, so an old failure no longer dominates the suggested next action after a successful retry.
- Chat live work now prints compact `Next controls` after live steps, keeping primary continue/follow plus resume/help visible while leaving full controls to startup and `/work-session`.
- `/continue` now remembers the previous live-step options for the current chat session and treats plain text as `--work-guidance`, so a user can steer the next resident step without retyping gates.
- `mew chat --work-mode`, `/work-mode on`, and `/c` reduce cockpit typing: text becomes `/continue` guidance, blank lines repeat only after a work step has run, and `/c` is a short continue alias.
- `mew work --follow` and chat `/follow` provide a compact continuous live loop that defaults to 10 steps, streams model progress, shows a separated model-stream preview in the thinking pane, and stops at existing resident boundaries such as finish, failures, stop requests, pending approvals, or user interrupt.
- Ctrl+C during `--follow` marks the current running model turn/tool as interrupted, records a durable resume note, and preserves chat continue options instead of leaving the next `/c` blocked by a stop request.
- When `--follow` or a multi-step live run reaches `--max-steps`, mew records a system work-session note with the final action/result and reentry hint, so bounded loops leave a durable explanation even if the model spent the final step observing.
- Pending write approval hints now reuse the latest session verification command when available, reducing the chance that an approval prompt shows only a placeholder.
- Write approval execution can now reuse the latest session verification command when `--verify-command` is omitted, while still requiring explicit write roots.
- Successful `run_tests` and write verification results now refresh the session default verification command, preventing reentry controls from preserving a known-stale verifier after a better command succeeds.
- Work-session resume next-action text now points at `/continue` and `mew work --live`, matching the current cockpit path instead of older `/work-session ai` guidance.
- `mew chat --help` now includes the slash-command reference, and `/help work` prints focused work-session reentry/continue commands.
- `mew chat` appends local input transcript entries to `.mew/chat.jsonl`, and `mew chat-log` plus `/transcript` expose recent chat inputs without mixing them into runtime activity output.
- `mew effects 10` and `mew runtime-effects 10` now accept positional limits like the chat command forms, reducing CLI/chat grammar mismatch.
- `mew do <task-id>` now provides a compact supervised resident coding entrypoint over `mew work --live`, defaulting to deterministic ACT, read/write roots at `.`, and an auto-detected verification command when available.
- Model-selected `run_tests` now refuses resident mew loops such as `mew do`, `mew chat`, `mew run`, and `mew work --live`, preventing a supervised session from treating another resident loop as its verifier.
- `mew work --session`, `mew work --session --resume`, and `/work-session` now fall back to recent work sessions when no session is active, including exact CLI and chat resume hints.
- `mew work --session --json` and `mew work --session --resume --json` expose the same recent-session summaries for model-facing or scripted reentry.
- Active `mew work --session --json` and `--resume --json` now include structured `next_cli_controls`, preserving continue/stop/resume/chat commands for machine readers.
- Active `mew work --session`, active `/work-session`, and normal `mew chat` startup now surface next controls for continuing, stopping, resuming, or entering chat.
- Text resume surfaces (`mew work --session --resume` and `/work-session resume`) now print controls after the compact resume bundle.
- Quiet `mew chat --no-brief` startup still surfaces active work-session controls, so suppressing the brief does not remove the reentry affordance.
- `mew focus` / `mew daily` now surface active work sessions with phase, next action, resume command, and one-step continue command, making task reentry visible from the quiet daily view.
- `mew focus` now includes active work-session working memory when present, so the quiet daily view can show the resident model's current hypothesis and memory next step before opening a full resume.
- `mew focus` now marks stale work-session memory and suppresses stale `memory_next` text when later tool or model activity means the resident should refresh before relying on it.
- `mew focus` now reuses the active work session's saved model/gate/verify/approval defaults in its continue/follow commands, so daily reentry stays copy-paste runnable.
- `mew digest` exposes the chat digest as a top-level command, making recent autonomous activity review available without entering the chat REPL.
- Active sessions remember start/live read/write/verify/model/approval options and reuse them in later CLI/chat controls, reducing repeated gate flag entry after reentry.
- Chat work-session Inspect and Advanced controls now reuse the active session's saved/default read roots instead of falling back to `--allow-read .`, keeping scoped cockpits from suggesting broader or invalid read gates.
- Chat `/work-session resume <task> --allow-read <root>` now carries that explicit read root into the printed Next controls and cached `/c` options, so scoped resume does not immediately suggest broader `--allow-read .` follow-ups.
- Scripted non-interactive `mew chat` defers startup controls when the first input is a work-session/continue command, so scoped command results are not preceded by generic active-session controls.
- Manual `run_tests` / `run_command` calls no longer store the parser's default `--path .` as a touched file, so non-file actions do not create noisy `.` world-state warnings.
- Missing-executable verification failures now keep JSON `exit_code: null` but render human-facing resume/commands/tests output as `exit=unavailable` with `executable not found: ...` context.
- Missing-executable command records now normalize stderr to `executable not found: ...`, so focused command/test panes no longer leak raw Python `[Errno 2]` text.
- Live work progress now flushes stdout before stderr progress lines, reducing apparent reordering where model delta prose could appear after `ACT ok` progress in mixed streams.
- Follow/live max-step boundary notes are shorter and replace older system max-step boundary notes in the same session, reducing repeated reentry material while keeping model/tool history for audit.
- Partial reentry-option updates now preserve existing read/write/verify/model defaults and add new explicit roots, so a later read-only command does not erase previously useful write or verification gates.
- CLI live controls now prefer the current command's explicit tool gates over saved broader defaults, so read-only reentry does not suggest stale write, shell, or verification permissions.
- Starting a new work session for a task with only closed sessions now clones the latest closed session defaults, preserving cockpit gates across closed-session restart.
- CLI/chat controls now show both one-step continue and bounded `--max-steps 3` continue paths, making short autonomous runs discoverable without removing the safer single-step path.
- Multi-step work loops stop at pending dry-run write approvals, preserving the human review boundary while allowing bounded autonomous read/verify progress.
- Fresh `mew chat` `/continue <guidance>` now falls back to the active work session's stored defaults when the current chat state has no cached options, preserving read/auth/model gates after reentry.
- Default `mew work --session` and `/work-session` tool-call views compact read/search/glob results, keeping reentry quiet even when prior `read_file` calls captured large text.
- Work-session world-state formatting no longer labels nonzero `git_status` as `(clean)`; it surfaces stderr/stdout so non-git workspaces are not misrepresented.
- Work-session world-state git summaries filter `.mew/` internal state noise, so reentry does not make mew's own persistence look like project dirt.
- `mew next` and passive next-move messages now route unplanned coding tasks to `mew work <task-id> --start-session`, matching native hands as the first execution path.
- Chat work-session parsing accepts task-first resume order such as `/work-session 26 resume --allow-read .`, reducing command-order friction during reentry.
- Work-session resume bundles now expose a compact `phase` such as `idle`, `awaiting_approval`, `running_tool`, `planning`, `interrupted`, or `closed`, giving the cockpit and resident prompt a clearer state label.
- The same phase is visible in normal workbench/work-session views, so the user does not need to open the full resume just to know the current state.
- `mew work --live` now prints a resume bundle after control actions such as `finish`, so live sessions end with the closed-session state visible instead of only an action line.
- `mew work --live` now preflights missing tool gates and prints concrete reentry controls before calling the model, avoiding a wasted model turn that can only fail on permissions.
- Native work sessions now support a stop request (`mew work --stop-session` and `/work-session stop`) that is consumed at the next model/tool boundary before another model call starts.
- Stop requests leave their reason in the work report and resume bundle after they are consumed, preserving why a live loop paused.
- Work model turns are now journaled as `running` before THINK/ACT starts, so resume can show `phase=planning` during an in-flight model call and repair has real state to interrupt if the process dies.
- Stop requests are checked again after THINK/ACT, immediately before a selected tool starts, and between batch subtools, so a pause request prevents the next tool call at real execution boundaries.
- CLI `mew work --live` runs now end with `Next CLI controls`, showing continue, stop, resume, and chat commands for the current session.
- `dogfood --scenario work-session` now covers stop request recording and `phase=stop_requested` resume output.
- `dogfood --scenario work-session` now also covers user session notes appearing in resume output.
- Model-selected `read_file` now defaults to a smaller 12,000-character page, and model-selected `git_diff` defaults to diffstat unless full diff is explicitly requested, reducing the chance that a broad read-only batch bloats a resident session.
- Work-mode prompts now tell the resident model that current capability gates are authoritative, reducing stale permission-failure loops where it asks for a flag already present.
- Work-mode prompts now tell the resident model that `run_command` is shlex-parsed without a shell, reducing failed probes that use `&&`, pipes, or redirection.
- Work-mode prompts now steer code navigation toward `search_text` before broad `read_file`, then line-window reads from search hits, reducing wasted context in compact live dogfood.
- Nonzero `run_command` exits now surface in work-session failure summaries and `phase=failed` without treating the command launch itself as a tool crash.
- Work-mode prompts now treat one-shot `--work-guidance` / `/continue <guidance>` as the current instruction for that turn, reducing early `finish` decisions based only on older session notes.
- Work-session model turns now retain a clipped `guidance_snapshot` copy of that one-shot guidance, and resume, timeline, details, and model context expose it for reentry and audit without making it current guidance again.
- Work-session guidance previews now clip on a one-line word boundary, keeping recent decision/reentry guidance readable instead of corrupting intent with mid-word truncation.
- `mew next --kind coding`, `mew focus --kind coding`, and chat `/next coding` / `/focus coding` expose the next coding-shell move without being blocked by unrelated open research or personal questions.
- `mew self-improve --native`, `mew self-improve --start-session`, and chat `/self native ...` / `/self start ...` create/reuse a self-improvement coding task without forcing the older programmer-plan path, then print or start the native work-session path.
- When the coding queue is empty, `mew next --kind coding` / `mew focus --kind coding` now suggest starting a native self-improvement session rather than going silent.
- `mew work --approve-tool` now accepts exact new-file write roots when the parent directory exists, so resume-suggested file-level approvals apply correctly without broadening the write gate to `.`.
- Unresolvable write roots now explain that the parent directory must exist instead of reporting a misleading `write is disabled` error when `--allow-write` was supplied.
- `mew work <task-id>` now surfaces the latest work-session write and verification ledgers, including closed sessions, so the task workbench no longer says `Verification (none)` / `Writes (none)` after verified native work.
- `mew work <task-id>` now surfaces a compact `Reentry` block with work-session working memory, recent user/model notes, latest decision guidance, task notes, and resume/chat hints, making the top-level task workbench a usable front door for resident continuation.
- `mew verification` and `mew writes` now include work-session tool calls with stable `source`, `id`, `ledger_id`, and session-qualified labels such as `work25#113.verify`, making native work audit trails visible outside the full session view.
- `mew status --kind ...` and `mew brief --kind ...` now scope counts, unread task-linked messages, questions, attention, task queues, next moves, and brief ledgers by task kind; kind-scoped briefs suppress unrelated global activity/thought/step history.
- Human-role E2E round 3 verified that `brief --kind coding`, `status --kind coding`, missing-parent write-root errors, and global work-session ledgers all behave as intended without tracked file edits.
- `mew chat --kind ...` now scopes the startup brief, unread outbox, and slash-command views; `/scope` can switch or clear the active chat kind, and `mew listen --kind ...` scopes passive outbox observation.
- Chat `/work` now respects the active kind scope when selecting a default task, so a `mew chat --kind coding` cockpit no longer silently opens unrelated research work.
- Chat startup, `/work-session`, `/work-session live`, `/work-session resume`, `/work-session timeline`, approvals, rejections, stop, and notes now respect the active chat kind scope when no explicit task id is supplied.
- Chat `/continue` now accepts stored options followed by plain guidance, preserving reusable gates like `--auth` / `--allow-read` while treating the trailing text as one-shot work guidance.
- `mew work --live` now defaults to deterministic ACT, so the common live path uses one model call per step; model JSON/text deltas are quiet by default and remain available with explicit `--stream-model`.
- `read_file` now supports `line_start` / `line_count` through both CLI tools and resident model actions, letting the model jump from `search_text` line numbers to the relevant source region instead of rereading file offset 0.
- Invalid line-based `read_file` requests now fail clearly (`line_start must be >= 1`), while out-of-range line reads return structured EOF metadata and summaries like `lines=99-EOF`.
- Line-window reads now distinguish `has_more_lines` from `truncated`, so a fully returned requested window can expose `next_line` without falsely saying the returned text was truncated.
- Compact work-session timelines now preserve failed/interrupted tool errors instead of formatting failed `read_file` calls as empty offset reads.
- Failed/interrupted timeline summaries now avoid duplicate labels such as `read_file failed: read_file failed: ...`.
- Generated cockpit commands now prefer `./mew ...` when the current checkout has an executable local wrapper, making next controls copy-paste runnable in source worktrees where `mew` is not installed on `PATH`.
- Text outbox/listen/chat history views now clip very large message bodies and point to `outbox --json` for the full payload, reducing the chance that historical agent payloads swamp the cockpit.
- `edit_file` now permits small exact replacements in large files by limiting replacement/delta size instead of rejecting based on total edited file size.
- `mew work --live` dogfood task #44 used Codex Web API as a resident buddy: it exposed the missing line-based read path, exposed the large-file small-edit blocker, retried after those fixes, produced dry-run edit #133, and approved it with `uv run pytest -q`.
- `dogfood --scenario work-session` now covers line-based `read_file`, large-file dry-run `edit_file`, focused diff previews, and focused test output, bringing the recurring scenario to 29 commands.
- `dogfood --scenario chat-cockpit` now exercises a scripted `mew chat --kind coding` session with `/scope`, `/tasks`, `/work`, scoped startup controls, scoped `/work-session`, and chat transcript logging, making the scoped cockpit path part of deterministic recurring dogfood.

Missing proof:

- Model delta streaming and a separated thinking-pane preview now exist and work against the live Codex Web API, but the reasoning/status pane still needs longer dogfood and polish before it is comparable to Claude Code / Codex CLI.
- `mew chat --work-mode`, `/c`, and bounded `/follow` now reduce cockpit friction, but the broader resident coding loop still needs more long-session dogfood before it can replace a mature coding CLI.
- Batch support removes the strict one-tool limit for read-only inspection, but applied writes, shell commands, and verification still run one tool at a time.
- Large active-session growth is now visible and recent file reads are clipped in model context, but there is no global prompt budget enforcement or semantic compaction of noisy work-session history.
- Live coding work session UX now has focused help, one-step `/continue` and `/c`, reusable options, chat work-mode with guarded blank repeats, bounded follow loops, inline guidance capture, boundary stop requests, interrupt and max-step reentry notes, recent-session reentry, compact chat controls, focused diff/test panes, scoped status/brief views, and global work-session ledgers, but it is still not a full REPL-style coding cockpit with polished reasoning/status flow.

Next action:

- Dogfood the live cockpit on real repository investigations, then improve the reasoning/status pane and long-session output pacing so a chat work session feels closer to Claude Code / Codex CLI.

## Milestone 3: Persistent Advantage

Status: `in_progress`

Evidence:

- Durable state tracks tasks, questions, inbox/outbox, agent runs, step runs, thoughts, and runtime effects.
- Context builder includes recent runtime effects and clipped summaries.
- Project snapshot and memory systems exist.
- Native work sessions now have task-local resume bundles with files touched, commands, failures, pending approvals, working memory, recent decisions, next action, and context pressure.
- The resident work model receives the resume bundle in its prompt, so separate invocations can continue from task-local work history.
- Recent work model turns now feed bounded prior THINK/reasoning fields back into the next prompt, so the resident model can carry observations and hypotheses between steps instead of relying only on raw tool output.
- THINK prompts now ask the resident model to persist a compact `working_memory` object for future reentry; old sessions fall back to latest turn summary/action reason plus verification state.
- Working memory treats observed verification results as authoritative over model-written verification claims and marks the digest stale when later model turns did not refresh it.
- Work mode now has a `remember` control action that records durable session notes surfaced in resume bundles and future model context.
- Humans can add the same durable work-session notes with `mew work --session-note` or `/work-session note`, making persistent guidance distinct from one-shot `/continue` guidance.
- Work model context now carries a bounded `session_knowledge` digest for older tool calls that have fallen out of the full recent tool-call window, preserving what was inspected without raw file contents.
- Work model context now includes a bounded live `world_state` summary when read access is allowed, so resumed work can compare durable history with current git/file metadata.
- Recent read-file results are clipped for model context with a resume offset, so long-running sessions keep enough local detail to continue without repeatedly embedding large source files.
- Work model context now enforces a budget by shrinking recent tool/turn windows and adding a `context_compaction` note when the work-session JSON grows too large.
- Work model context now clips task notes by recent lines and tail length, so recent recommendations and corrections survive when old self-improvement notes have accumulated.
- Work-session `finish` notes now prefer explicit action summaries over boundary reasons, keeping task notes useful for future reentry.
- `mew task show` and chat `/show` now clip long task notes to recent lines, so human reentry views do not drown in old self-improvement session endings.
- Work-session write and verification records now appear in global `mew writes` / `mew verification` ledgers with stable identifiers, so task-local work history is discoverable without reopening raw session JSON.
- Kind-scoped `mew status --kind coding` and `mew brief --kind coding` provide a calmer task/coding reentry view that is not dominated by unrelated research questions or unread outbox.

Missing proof:

- Task-local resume and scoped reentry views exist for native work sessions, but they are not yet proven across day-scale interruption/resume cycles.
- There is no semantic compaction strategy for noisy long-running work-session history beyond archive retention, explicit `remember` notes, automatic working-memory digests, older-tool digests, read-result clipping, and budgeted recent-window compaction.
- No watcher-driven passive updates.
- User preference memory is not yet clearly shaping behavior.

Next action:

- Use task-local resume as the basis for day-scale reentry: compact noisy history, keep open risks, and verify that returning after interruption is faster than starting a fresh CLI session.

## Milestone 4: True Recovery

Status: `foundation`

Evidence:

- Runtime effects persist lifecycle status.
- `mew doctor` detects incomplete runtime cycles/effects.
- `mew repair` can mark unfinished effects as `interrupted`.
- Interrupted effects receive `recovery_hint`.
- Runtime effects now record user-visible `outcome`.
- `mew repair` now marks stale `running` work-session tool calls and model turns as `interrupted` with a recovery hint, so native work resumes do not keep ambiguous in-flight state forever.
- Interrupted work-session items surface as `phase=interrupted` in the resume bundle with a conservative next action.
- `mew work --recover-session --allow-read ...` can retry interrupted read-only work tools and mark the original interrupted call as superseded; `mew work --session --resume --allow-read ... --auto-recover-safe` and `/work-session resume --allow-read ... --auto-recover-safe` can opt into the same safe read/git retry while showing the refreshed resume. Safe retries record `world_state_before`; write/shell/verification recovery remains gated by human review.
- Interrupted work-session resumes now include a recovery plan that classifies retryable read/git tools, replannable model turns, and side-effecting work that needs human review.
- Retryable read/git recovery plan items now include manual, automatic CLI, and chat auto-recovery hints.
- Side-effecting interrupted command/write recovery items now include the original command or path, a review hint, and short review steps; `mew work --recover-session --json` reports the same review context instead of only refusing automatic retry.
- Interrupted command summaries now fall back to stored parameters when no result exists, non-JSON recovery output prints command/path review context, and pending stop requests appear directly in resume JSON/text.
- `save_state` now rotates the previous `state.json` to `state.json.bak` before replacing it, giving the resident shell a simple recovery point if the current state file is damaged.
- `mew work --session --resume --allow-read ...` now adds a live world-state section with current git status and touched-file stats, reducing reliance on cached session history alone.
- The same world-state check is available from chat resume and in model context, making it easier for both user and resident model to revalidate state before continuing.

Missing proof:

- No automatic resume/retry/abort/ask_user decision from interrupted runtime effects, and no automatic recovery for interrupted write/shell/verification work items.
- World-state revalidation before retry exists for safe read/git work-session recovery, but not yet for runtime effects or side-effecting work.
- Safe work-session auto-recovery is still opt-in and limited to one interrupted read/git tool per resume.

Next action:

- Implement interrupted effect classification and safe next-action selection.

## Milestone 5: Self-Improving Mew

Status: `foundation`

Evidence:

- `mew-product-evaluator` skill exists.
- Dogfood scenarios exist and are used.
- Self-improvement task creation/planning paths exist.
- External model review through ACM has been used for roadmap and extraction decisions.
- `mew-roadmap-status` skill and this status file exist to preserve roadmap progress across context compression.
- Native self-improvement dogfood tasks #36-#39 produced and validated small mew fixes: low-intent research wait suppression, stale done-task work-session filtering/closing, and recent-commit/coding-focus context for future self-improvement sessions.
- Native self-improvement dogfood task #44 used `mew work --live` with Codex Web API to discover and drive line-based reads, large-file edit support, and a cockpit `/continue` display improvement.

Missing proof:

- mew does not yet run repeated self-improvement loops with native tools.
- Human approval/checkpoint flow is still manual.
- Self-improvement is not yet primarily driven by mew's own resident loop.
- Roadmap/status files are governance support, not proof of autonomous self-improvement.

Next action:

- Once Native Hands exists, dogfood a small self-improvement task end-to-end inside mew.

## Latest Validation

- `uv run pytest -q` current: `633 passed, 4 subtests passed`.
- `uv run pytest -q tests/test_codex_api.py tests/test_work_session.py::WorkSessionTests::test_work_ai_can_stream_model_deltas_to_progress tests/test_work_session.py::WorkSessionTests::test_work_follow_streams_model_deltas_by_default` current: `4 passed`.
- `uv run pytest -q tests/test_work_session.py` current: `139 passed`.
- `uv run pytest -q tests/test_dogfood.py tests/test_work_session.py` current: `134 passed`.
- `uv run pytest -q tests/test_work_session.py tests/test_write_tools.py` current: `98 passed` (last observed before the latest approval-continuity tests).
- `uv run pytest -q tests/test_commands.py` current: `131 passed, 4 subtests passed`.
- `uv run pytest -q tests/test_commands.py tests/test_brief.py` current: `162 passed, 4 subtests passed`.
- `uv run pytest -q tests/test_dogfood.py` current: `31 passed`.
- `uv run pytest -q tests/test_self_improve.py` current: `16 passed` (last observed in this long-session cycle before the latest cockpit edits).
- `uv run pytest -q tests/test_dogfood.py::DogfoodTests::test_run_dogfood_chat_cockpit_scenario tests/test_dogfood.py::DogfoodTests::test_run_dogfood_work_session_scenario` current: `2 passed`.
- `uv run python -m compileall -q src/mew` current: pass.
- `uv run mew dogfood --scenario chat-cockpit --cleanup` current: pass, including scoped chat startup, scoped `/tasks`, scoped `/work`, scoped active-session controls, scoped `/work-session`, `/follow` discoverability, `/work-mode` toggles, and chat transcript logging.
- `uv run mew dogfood --scenario work-session --cleanup` current: pass, including exact new-file approval, pending diff preview in resume, command-output previews in resume, working-memory resume surfacing, focused chat diff/test/command previews, line-based read, large-file dry-run edit, workbench/global work-session ledgers, chat resume world state, timeline surfacing, side-effect recovery review context, safe read auto-recovery, and 31 commands.
- `uv run mew dogfood --scenario all --cleanup` current: pass, including `chat-cockpit` with transcript logging and `work-session`.
- `uv run mew doctor` current: state/runtime/auth ok.
- `codex-ultra` focused reviews of the low-intent wait guard, stale work-session filtering/closing, and self-improvement context changes found no concrete issues after fixes.
- `mew work --live` dogfood as a self-improvement buddy exposed repeated stale-topic selection; self-improvement descriptions now put recent completed commits before a coding-only focus view.
- `codex-ultra` focused re-review of stop/context/recovery fixes: no concrete remaining issues found.
- `codex-ultra` read-only external-use test: usable for short bounded resident coding sessions; main remaining gap is the REPL-style cockpit and reentry discovery.
- `codex-ultra` reentry retest after cockpit changes: strict chat resume order and missing chat resume hints are mostly fixed; remaining UX gaps are broader cockpit polish and quiet-chat affordances.
- `codex-ultra` human-role E2E round 2 verified exact `/tmp` new-file approval, sibling write rejection, work-session/global ledgers, and `uv run pytest tests/test_work_session.py -q` with `88 passed`.
- `codex-ultra` human-role E2E round 3 verified that `brief --kind coding`, `status --kind coding`, missing-parent write-root errors, and global work-session ledgers pass without tracked file edits.
- `codex-ultra` approval-UX human-role E2E after inline defaults verified pending diff previews, explicit and TTY-default inline prompts, verifier display, opt-out behavior, verification/writes ledgers, and clean repo state. It found two continuity bugs: generated controls dropped `--no-prompt-approval`, and `approve-tool` ignored session default verification commands; both now have regression tests and fixes.
- `codex-ultra` approval-UX retest after continuity fixes verified that `--no-prompt-approval` stays in next controls without reintroducing `--prompt-approval`, CLI and chat approvals reuse default verification commands, and focused `--diffs`/`--tests` plus `/work-session diffs`/`tests` show useful cockpit panes. No remaining bug was found in that scope.
- `claude-ultra` review of the working-memory reentry slice found two correctness concerns: model-written verification claims could outlive later failed tests, and old memory could shadow newer turns. Both are fixed with observed verification override, stale markers, and regression tests; Claude re-review reported no blockers.
- Work-session unit coverage now includes a deterministic resident THINK path proving model-returned `working_memory` is journaled and surfaced in the resume, not only manually synthesized state.
- `claude-ultra` review during the 2026-04-17 long session judged mew materially closer to a usable AI shell/body and identified live cockpit fluency, recovery breadth, and day-scale persistence as the top blockers.
- `claude-ultra` recheck after the 2026-04-17 cockpit work started successfully and identified `/work` scope leakage and mixed `/continue` options+guidance as the highest-leverage cockpit bugs; both were fixed in commit `1f97120`.
- `claude-ultra` Milestone 2 review after pending diff previews judged the cockpit direction coherent and recommended consolidating inline approval as the next small slice; interactive live/do approval prompts now have explicit default/force/opt-out semantics.
- Isolated `codex-ultra` agent-as-human E2E in `/tmp/mew-agent-human-role-20260417-013828` ran `chat-cockpit`, `work-session`, `all`, manual `chat --kind coding`, work-session reentry, line reads, and a live read-only resident model step. It judged mew usable for narrow task-coding shell work and found three papercuts: source-checkout command prefixes, timeline failure summaries, and line-window truncation wording; all three were fixed in commit `4e8ecf1`.
- Isolated `codex-ultra` retest in `/tmp/mew-agent-human-role-retest-20260417-015606` verified the three papercut fixes: `./mew` next controls, timeline failure text, and line-window `has_more_lines` without `(truncated)`; `chat-cockpit` dogfood also passed.
- `mew chat --kind coding`, `mew next --kind coding`, and `mew status --kind coding` were dogfooded locally after the scoped-chat changes; startup and slash-view scoping stayed quiet and task/coding-focused.
- `mew work --live` task #44 dogfood verified the quieter deterministic live path, then used line-based reads and large-file edit support to reach and approve a real cockpit improvement.
- `claude-ultra` reviews found no ship-blockers after fixes for work-session global ledgers and status/brief kind scoping.
- Mew dogfood task #27 used `mew work --live` with Codex Web API in this repository; it found high context pressure from broad batch reads, which led to smaller model read defaults and diffstat-first model `git_diff`.
- Mew dogfood task #28 used `mew work --live` with Codex Web API as a read-only self-improvement buddy; it reentered docs, chose `finish`, and exposed the need to distinguish session finish from task completion.
- `codex-ultra` distracted-user dogfood found that generated live/continue controls failed when only `~/.codex/auth.json` existed; work/do/chat defaults now preserve normal auth fallback instead of baking in `--auth auth.json`.
- `claude-ultra` product evaluation at HEAD before inline approval judged mew `NOT_YET` versus Claude Code/Codex CLI, with the top one-hour recommendation to add an inline live write approval loop; `--prompt-approval` is now the first implementation slice of that recommendation.
- `codex-ultra` focused retest after live-gate preflight, inline approval, interrupted recovery context, active-focus surfacing, and state backup found no concrete regressions in that scope.
- `codex-ultra` human-role retest after the follow/work-mode slice verified four targeted fixes: explicit `--follow --max-steps 1` is honored, chat `/follow` controls include `--max-steps 10`, world-state git status uses allowed repo roots from disposable cwd, and `glob` skips cache/venv directories. Repo status stayed clean.
- `claude-ultra` review after the follow interrupt/streaming/max-step work judged mew coherent but not yet preferred over Claude Code/Codex CLI; top blockers were thin streaming UX, shallow interrupt cancellation, and max-step note scope.
- `codex-ultra` human-role cockpit dogfood verified `/c`, `/follow`, max-step notes, and Ctrl+C reentry in a temporary workspace. It judged mew usable for short bounded read-only coding sessions and found three papercuts: sharp initial work-mode blank lines, repeated full controls, and verbose max-step notes; all three now have focused fixes and regression tests.
- Mew dogfood task #46 used `mew work --follow` with Codex Web API as a resident buddy after the 2026-04-17 cockpit changes; it verified grouped result panes with duration output and recorded that the remaining live-output gap was dense tool-result rendering, which led to multiline section indentation and direct command cwd/stdout/stderr rendering.
- `codex-ultra` human-role retest after the 2026-04-17 cockpit transcript work found three issues: non-git initial world-state resume showed `(no files)`, stale working memory rendered an old `next_step` too strongly, and `effects 10` / `runtime-effects 10` failed despite analogous chat grammar. Follow-up retest verified all three fixed with no repo edits.
- Live Codex Web API dogfood on task #46 exposed that SSE responses can omit `content-type`, causing final text to work while live deltas were dropped; after the fix, session #40 showed batched `model_delta` lines in the thinking pane with no stderr token spam.
- Mew buddy dogfood on task #46 exposed that one-line `search_text` hits could make the resident model misread ROADMAP_STATUS; after adding bounded context snippets and clarifying the status wording, session #44 correctly distinguished shipped cockpit panes from the remaining live reasoning/status-pane gap.
- Live Codex Web API dogfood on task #46 session #45 verified compact follow no longer repeats the same raw JSON in both `model_delta` and `stream_preview`; the planning summary kept `model_stream` metrics plus summary/reason.
- `claude-ultra` evaluation after the live-delta/search-snippet work said mew is conditionally worth inhabiting for short bounded coding tasks, but still behind Claude Code/Codex CLI for sustained interactive coding; its top 1-2 hour recommendation was readable compact rendering of plan-shaped model deltas.
- Live Codex Web API dogfood on task #46 session #46 verified compact follow now emits readable `model_summary_delta`, `model_action_delta`, and `model_reason_delta` lines instead of raw JSON `model_delta` text.
- Focused local validation verified that chat `/work-session` Inspect and Advanced controls now preserve a scoped `--allow-read sample` default and no longer suggest `--allow-read .` for that session.
- `codex-ultra` isolated human-role E2E after search-snippet/live-delta work judged mew usable for bounded supervised coding/task work and found six papercuts: model-delta ordering, mid-word guidance clipping, chat read-gate broadening, `.` touched-file noise, missing top-level workbench reentry notes, and missing-executable `exit=None` wording. This session fixed the read-gate broadening, guidance clipping, touched-file noise, top-level reentry block, and missing-executable wording.
- `claude-ultra` priority review ranked `mew work <task>` missing reentry guidance as the highest-leverage front-door issue and mid-word guidance clipping second; both are fixed in this session.
- `codex-ultra` retest after those fixes found that CLI scoped resume preserved read roots, but chat `/work-session resume <task> --allow-read <root>` still printed broadened Next controls and command/test panes still showed `exit=None`; both follow-up issues are now fixed with regression tests.
- `codex-ultra` focused retest of chat scoped resume controls and missing-executable panes passed against the current implementation: scoped slash-command resume printed `sample` controls, no `.` controls appeared in that command block, and resume/commands/tests panes used `exit=unavailable` plus normalized `executable not found` text. The agent noted its final clean-tree check saw concurrent local edits from this session, not test-created changes.
- Mew dogfood session #48 used Codex Web API as a read-only buddy after the front-door workbench change; it reentered task #46, inspected `ROADMAP_STATUS.md`, and recorded the next non-duplicative Milestone 2 slice as stabilizing the continuous reasoning/status pane and reducing repeated reentry material during long sessions.
- Mew dogfood session #48 later verified the live working-memory pane with real Codex Web API output: the closed live result printed `memory_hypothesis`, `memory_next`, and `memory_verified` in the compact `session` section.
- `codex-ultra` cockpit evaluation recommended the smallest next slice as surfacing active work-session `working_memory` inside the live result cockpit; this is now implemented in `format_work_live_step_result` with stale-memory labeling.
- `claude-ultra` cockpit evaluation recommended a recurring-failure ribbon for repeated tool failures; this is now implemented by deriving repeated tool/target/error groups from existing work-session history and surfacing them in resume/live result views.
- Focused dogfood of `mew work <task-id>` after the recurring-failure slice exposed old system max-step boundary notes crowding the front-door reentry block; workbench reentry now prefers user/model notes and hides those boundary notes while full resumes keep the audit trail.

## Current Roadmap Focus

Milestone 2: Interactive Parity.

The next implementation should make the new `mew chat --work-mode` / `/follow` path calmer in longer real coding sessions: improve the live reasoning/status pane, reduce repeated reentry material further, and keep dogfooding against repository tasks until the cockpit feels preferable to delegating back to Claude Code or Codex CLI.
