# Mew Roadmap Status

Last updated: 2026-04-16

This file tracks progress against `ROADMAP.md`. Keep it evidence-based and conservative.

## Summary

| Milestone | Status | Short Assessment |
|---|---|---|
| 1. Native Hands | `done` | `mew work --ai` can inspect, edit, verify, resume, and expose an audit trail without delegating to an external coding agent. |
| 2. Interactive Parity | `in_progress` | `mew work --ai` now has model/command streaming, live action/resume output, chat approval/live controls, context pressure diagnostics, and live world-state resume; the remaining gap is a polished REPL-style cockpit. |
| 3. Persistent Advantage | `in_progress` | Task-local resume, durable work notes, older-tool digests, and live world-state context now exist; day-scale reentry and passive watcher advantage are not yet proven. |
| 4. True Recovery | `foundation` | `doctor`, `repair`, runtime effect journal, `recovery_hint`, and `outcome` exist; automatic safe resume is not implemented. |
| 5. Self-Improving Mew | `foundation` | Self-improvement and dogfood entry points exist; closed-loop self-improvement is not yet reliable. |

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

- Move roadmap focus to Milestone 2: streaming/live coding parity, especially readable diff display, command output, and chat cockpit control for active work sessions.

## Milestone 2: Interactive Parity

Status: `in_progress`

Evidence:

- `mew chat` exists.
- Chat can inspect focus, status, workbench, agents, verification, writes, thoughts, runtime effects, doctor, and repair.
- `mew work --session --details` and `/work-session details` expose touched files, model turns, and tool-call summaries for the active work session.
- `mew work --ai` streams progress events to stderr in normal mode, and with `--progress` when JSON output is requested.
- Work-session details now include a `Recent diffs` section for write/edit tool calls, including verification exit code and rollback state.
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
- `mew work --session --resume --allow-read ...` and `/work-session resume --allow-read ...` add live git status and touched-file stats to the resume, and the same bounded world-state summary is injected into future work-model context when read access is allowed.
- `mew work --live` runs the resident work loop with progress and prints a resume bundle after each completed tool step.
- `mew archive` now archives closed work sessions, which gives large work-session histories a retention path after read/context limits increased.
- `read_file` supports `offset` and returns `next_offset`, letting the resident model page through files larger than one read window.
- Codex SSE text deltas can be forwarded into work progress with `--stream-model`; `--live` enables the same model-delta stream when the backend supports it.
- `mew work --live` now prints the selected action, reason, key parameters, and tool-call id before execution, so the user can see what the resident model is about to do before the resume bundle appears.
- `/work-session live ...` provides a chat shortcut for the same live resident work loop, and pending write approvals in resume output include concrete `/work-session approve ...` and `/work-session reject ...` hints.
- Work-session resume output now reports context pressure (`tool_calls`, `model_turns`, recent chars, total chars, pressure), making large active-session growth visible to both humans and the model.
- A real Codex Web API dogfood run on task #21 used `mew work --live --act-mode deterministic` for two read-only steps; it selected `inspect_dir` then `read_file`, printed action/reason/resume/context pressure for each step, and made no repository writes.
- Work-mode control actions now have side effects: `send_message` writes to outbox, `ask_user` creates a normal question, and `finish` closes the work session while appending a final note to the task.
- Closed work sessions can still be inspected with `mew work <task-id> --session --resume`, so a finished resident work loop leaves a durable reentry/final-state artifact.
- `mew chat` now has `/continue ...` as a short one-step live command for the active work session, reducing the repeated `/work-session live ...` command burden.
- Work mode now supports a read-only `batch` action with up to five inspection tools in one model turn, journaling each tool call separately while keeping writes and shell commands outside batch mode.
- Codex Web API dogfood for batch exposed a missing `read_file.path` failure, after which batch normalization was hardened to skip invalid read subtools; retrying the same dogfood task completed `inspect_dir` and `read_file README.md` in one model turn without writes.
- Work-session resume next-action selection now keys off the latest tool result, so an old failure no longer dominates the suggested next action after a successful retry.
- Chat live work now prints `Next controls` after live steps, approvals, and rejections, making continue/resume/details/close actions visible without remembering commands.
- `/continue` now remembers the previous live-step options for the current chat session and treats plain text as `--work-guidance`, so a user can steer the next resident step without retyping gates.
- Pending write approval hints now reuse the latest session verification command when available, reducing the chance that an approval prompt shows only a placeholder.
- Write approval execution can now reuse the latest session verification command when `--verify-command` is omitted, while still requiring explicit write roots.
- Work-session resume next-action text now points at `/continue` and `mew work --live`, matching the current cockpit path instead of older `/work-session ai` guidance.
- `mew chat --help` now includes the slash-command reference, and `/help work` prints focused work-session reentry/continue commands.
- `mew work --session`, `mew work --session --resume`, and `/work-session` now fall back to recent work sessions when no session is active, including exact CLI and chat resume hints.
- `mew work --session --json` and `mew work --session --resume --json` expose the same recent-session summaries for model-facing or scripted reentry.
- Active `mew work --session --json` and `--resume --json` now include structured `next_cli_controls`, preserving continue/stop/resume/chat commands for machine readers.
- Active `mew work --session`, active `/work-session`, and normal `mew chat` startup now surface next controls for continuing, stopping, resuming, or entering chat.
- Text resume surfaces (`mew work --session --resume` and `/work-session resume`) now print controls after the compact resume bundle.
- Quiet `mew chat --no-brief` startup still surfaces active work-session controls, so suppressing the brief does not remove the reentry affordance.
- Active sessions remember live read/write/verify/model options and reuse them in later CLI/chat controls, reducing repeated gate flag entry after reentry.
- CLI/chat controls now show both one-step continue and bounded `--max-steps 3` continue paths, making short autonomous runs discoverable without removing the safer single-step path.
- `mew next` and passive next-move messages now route unplanned coding tasks to `mew work <task-id> --start-session`, matching native hands as the first execution path.
- Chat work-session parsing accepts task-first resume order such as `/work-session 26 resume --allow-read .`, reducing command-order friction during reentry.
- Work-session resume bundles now expose a compact `phase` such as `idle`, `awaiting_approval`, `running_tool`, `planning`, `interrupted`, or `closed`, giving the cockpit and resident prompt a clearer state label.
- The same phase is visible in normal workbench/work-session views, so the user does not need to open the full resume just to know the current state.
- `mew work --live` now prints a resume bundle after control actions such as `finish`, so live sessions end with the closed-session state visible instead of only an action line.
- Native work sessions now support a stop request (`mew work --stop-session` and `/work-session stop`) that is consumed at the next model/tool boundary before another model call starts.
- Stop requests leave their reason in the work report and resume bundle after they are consumed, preserving why a live loop paused.
- Work model turns are now journaled as `running` before THINK/ACT starts, so resume can show `phase=planning` during an in-flight model call and repair has real state to interrupt if the process dies.
- Stop requests are checked again after THINK/ACT, immediately before a selected tool starts, and between batch subtools, so a pause request prevents the next tool call at real execution boundaries.
- CLI `mew work --live` runs now end with `Next CLI controls`, showing continue, stop, resume, and chat commands for the current session.
- `dogfood --scenario work-session` now covers stop request recording and `phase=stop_requested` resume output.
- `dogfood --scenario work-session` now also covers user session notes appearing in resume output.
- Model-selected `read_file` now defaults to a smaller 12,000-character page, and model-selected `git_diff` defaults to diffstat unless full diff is explicitly requested, reducing the chance that a broad read-only batch bloats a resident session.

Missing proof:

- Model delta streaming is wired for Codex SSE, but live UX still prints raw JSON deltas rather than a polished reasoning view.
- Default THINK/ACT still uses two model calls per work step; deterministic ACT exists but needs more dogfood before it should become the default.
- Batch support removes the strict one-tool limit for read-only inspection, but applied writes, shell commands, and verification still run one tool at a time.
- Large active-session growth is now visible and recent file reads are clipped in model context, but there is no global prompt budget enforcement or semantic compaction of noisy work-session history.
- Live coding work session UX now has focused help, one-step `/continue`, reusable options, inline guidance capture, boundary stop requests, recent-session reentry, and next controls, but it is still not a full REPL-style coding cockpit with polished streaming and defaults for approval verification.

Next action:

- Dogfood the live cockpit on real repository investigations, then add polished streaming and safer approval defaults so a long chat work session feels closer to Claude Code / Codex CLI.

## Milestone 3: Persistent Advantage

Status: `in_progress`

Evidence:

- Durable state tracks tasks, questions, inbox/outbox, agent runs, step runs, thoughts, and runtime effects.
- Context builder includes recent runtime effects and clipped summaries.
- Project snapshot and memory systems exist.
- Native work sessions now have task-local resume bundles with files touched, commands, failures, pending approvals, recent decisions, next action, and context pressure.
- The resident work model receives the resume bundle in its prompt, so separate invocations can continue from task-local work history.
- Recent work model turns now feed bounded prior THINK/reasoning fields back into the next prompt, so the resident model can carry observations and hypotheses between steps instead of relying only on raw tool output.
- Work mode now has a `remember` control action that records durable session notes surfaced in resume bundles and future model context.
- Humans can add the same durable work-session notes with `mew work --session-note` or `/work-session note`, making persistent guidance distinct from one-shot `/continue` guidance.
- Work model context now carries a bounded `session_knowledge` digest for older tool calls that have fallen out of the full recent tool-call window, preserving what was inspected without raw file contents.
- Work model context now includes a bounded live `world_state` summary when read access is allowed, so resumed work can compare durable history with current git/file metadata.
- Recent read-file results are clipped for model context with a resume offset, so long-running sessions keep enough local detail to continue without repeatedly embedding large source files.
- Work model context now enforces a budget by shrinking recent tool/turn windows and adding a `context_compaction` note when the work-session JSON grows too large.

Missing proof:

- Task-local resume exists for native work sessions, but it is not yet proven across day-scale interruption/resume cycles.
- There is no semantic compaction strategy for noisy long-running work-session history beyond archive retention, explicit `remember` notes, automatic older-tool digests, read-result clipping, and budgeted recent-window compaction.
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
- `mew work --recover-session --allow-read ...` can retry interrupted read-only work tools and mark the original interrupted call as superseded; write/shell/verification recovery remains gated by human review.
- Interrupted work-session resumes now include a recovery plan that classifies retryable read/git tools, replannable model turns, and side-effecting work that needs human review.
- `mew work --session --resume --allow-read ...` now adds a live world-state section with current git status and touched-file stats, reducing reliance on cached session history alone.
- The same world-state check is available from chat resume and in model context, making it easier for both user and resident model to revalidate state before continuing.

Missing proof:

- No automatic resume/retry/abort/ask_user decision from interrupted runtime effects, and no automatic recovery for interrupted write/shell/verification work items.
- No world-state revalidation before retry.
- No recovery report after automatic resume.

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

Missing proof:

- mew does not yet run repeated self-improvement loops with native tools.
- Human approval/checkpoint flow is still manual.
- Self-improvement is not yet primarily driven by mew's own resident loop.
- Roadmap/status files are governance support, not proof of autonomous self-improvement.

Next action:

- Once Native Hands exists, dogfood a small self-improvement task end-to-end inside mew.

## Latest Validation

- `uv run pytest -q` current: `508 passed, 4 subtests passed`.
- `uv run pytest -q tests/test_work_session.py tests/test_commands.py` current: `175 passed, 4 subtests passed`.
- `uv run pytest -q tests/test_dogfood.py::DogfoodTests::test_run_dogfood_work_session_scenario` current: `1 passed`.
- `uv run python -m compileall -q src/mew` current: pass.
- `./mew dogfood --scenario work-session --cleanup` current: pass, including `chat_resume_surfaces_world_state`.
- `./mew dogfood --scenario all --cleanup` current: pass, including `work-session` with 13 commands.
- `./mew doctor --auth auth.json` current: state/runtime/auth ok.
- `codex-ultra` focused re-review of stop/context/recovery fixes: no concrete remaining issues found.
- `codex-ultra` read-only external-use test: usable for short bounded resident coding sessions; main remaining gap is the REPL-style cockpit and reentry discovery.
- `codex-ultra` reentry retest after cockpit changes: strict chat resume order and missing chat resume hints are mostly fixed; remaining UX gaps are broader cockpit polish and quiet-chat affordances.
- Mew dogfood task #27 used `mew work --live` with Codex Web API in this repository; it found high context pressure from broad batch reads, which led to smaller model read defaults and diffstat-first model `git_diff`.

## Current Roadmap Focus

Milestone 2: Interactive Parity.

The next implementation should turn `mew work --live` and `/work-session live` into a real resident coding cockpit: a continuous loop with visible action selection, controlled continuation, approval handling, and a durable final note that explains what changed or what should happen next.
