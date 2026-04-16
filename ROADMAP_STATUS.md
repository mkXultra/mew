# Mew Roadmap Status

Last updated: 2026-04-16

This file tracks progress against `ROADMAP.md`. Keep it evidence-based and conservative.

## Summary

| Milestone | Status | Short Assessment |
|---|---|---|
| 1. Native Hands | `done` | `mew work --ai` can inspect, edit, verify, resume, and expose an audit trail without delegating to an external coding agent. |
| 2. Interactive Parity | `in_progress` | `mew work --ai` now has model/command streaming, live action/resume output, chat approval/live controls, and context pressure diagnostics; the remaining gap is a polished REPL-style cockpit. |
| 3. Persistent Advantage | `foundation` | Durable state, memory, context, and runtime effects exist; automatic task resume context is still incomplete. |
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
- `dogfood --scenario work-session` now exercises chat `/work-session details`, so cockpit visibility is part of the recurring dogfood path.
- Native work reads now default to 50,000 characters and model work-session context keeps up to 20,000 characters per result, reducing the chance that a model loses the relevant half of a normal source file.
- Work sessions now expose read-only `git_status`, `git_diff`, and `git_log` tools behind the read gate, avoiding unnecessary `--allow-shell` for common coding context.
- `mew work --ai --act-mode deterministic` can skip the second model ACT call and normalize THINK output locally; the default remains model ACT to preserve the original THINK/ACT architecture.
- `mew work --session --resume` and `/work-session resume` produce a compact reentry bundle with touched files, commands, failures, pending approvals, recent decisions, and next action.
- The same resume bundle is included in work-mode model context so the resident model sees reentry state without reconstructing it from raw tool history.
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
- Work-session resume next-action text now points at `/continue` and `mew work --live`, matching the current cockpit path instead of older `/work-session ai` guidance.
- Work-session resume bundles now expose a compact `phase` such as `idle`, `awaiting_approval`, `running_tool`, `planning`, `interrupted`, or `closed`, giving the cockpit and resident prompt a clearer state label.

Missing proof:

- Model delta streaming is wired for Codex SSE, but live UX still prints raw JSON deltas rather than a polished reasoning view.
- Default THINK/ACT still uses two model calls per work step; deterministic ACT exists but needs more dogfood before it should become the default.
- Batch support removes the strict one-tool limit for read-only inspection, but applied writes, shell commands, and verification still run one tool at a time.
- Large active-session growth is now visible, but there is no prompt budget enforcement or automatic compaction of noisy work-session history.
- Live coding work session UX now has a one-step `/continue` command, reusable options, and inline guidance capture, but it is still not a full REPL-style coding cockpit with polished streaming, defaults for approval verification, and richer pause/stop state.

Next action:

- Dogfood the live cockpit on real repository investigations, then add polished streaming and safer approval defaults so a long chat work session feels closer to Claude Code / Codex CLI.

## Milestone 3: Persistent Advantage

Status: `foundation`

Evidence:

- Durable state tracks tasks, questions, inbox/outbox, agent runs, step runs, thoughts, and runtime effects.
- Context builder includes recent runtime effects and clipped summaries.
- Project snapshot and memory systems exist.
- Native work sessions now have task-local resume bundles with files touched, commands, failures, pending approvals, recent decisions, next action, and context pressure.
- The resident work model receives the resume bundle in its prompt, so separate invocations can continue from task-local work history.
- Recent work model turns now feed bounded prior THINK/reasoning fields back into the next prompt, so the resident model can carry observations and hypotheses between steps instead of relying only on raw tool output.

Missing proof:

- Task-local resume exists for native work sessions, but it is not yet proven across day-scale interruption/resume cycles.
- There is no automatic compaction or pruning strategy for noisy long-running work-session history beyond archive retention.
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

Missing proof:

- No automatic resume/retry/abort/ask_user decision from interrupted effects or interrupted work-session items.
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

- `uv run pytest -q` current: `476 passed, 4 subtests passed`.
- `uv run pytest -q tests/test_work_session.py` current: `35 passed`.
- `uv run pytest -q tests/test_codex_api.py tests/test_model_backends.py tests/test_work_session.py tests/test_dogfood.py::DogfoodTests::test_run_dogfood_work_session_scenario` current: `50 passed`.
- `uv run python -m compileall -q src/mew` current: pass.
- `./mew dogfood --scenario work-session --cleanup` current: pass.
- `./mew dogfood --scenario all --cleanup` current: pass, including `work-session`.
- `./mew doctor --auth auth.json` current: state/runtime/auth ok.

## Current Roadmap Focus

Milestone 2: Interactive Parity.

The next implementation should turn `mew work --live` and `/work-session live` into a real resident coding cockpit: a continuous loop with visible action selection, controlled continuation, approval handling, and a durable final note that explains what changed or what should happen next.
