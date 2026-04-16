# Mew Roadmap Status

Last updated: 2026-04-16

This file tracks progress against `ROADMAP.md`. Keep it evidence-based and conservative.

## Summary

| Milestone | Status | Short Assessment |
|---|---|---|
| 1. Native Hands | `done` | `mew work --ai` can inspect, edit, verify, resume, and expose an audit trail without delegating to an external coding agent. |
| 2. Interactive Parity | `in_progress` | `mew work --ai` now has progress events, streamed command output, detailed cockpit output, chat approval controls, and compact verification failure summaries; true model token streaming is still missing. |
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

Missing proof:

- Model delta streaming is wired for Codex SSE, but live UX still prints raw JSON deltas rather than a polished reasoning view.
- Default THINK/ACT still uses two model calls per work step; deterministic ACT exists but needs more dogfood before it should become the default.
- Work mode still executes one tool per model step.
- Large active sessions can now carry more context, so prompt size still needs monitoring while work is in progress.
- Live coding work session UX is improving, but it is still not a full REPL-style coding cockpit.

Next action:

- Build the first live work cockpit slice: visible model progress, current/pending tool action, and a clear continuation loop from chat.

## Milestone 3: Persistent Advantage

Status: `foundation`

Evidence:

- Durable state tracks tasks, questions, inbox/outbox, agent runs, step runs, thoughts, and runtime effects.
- Context builder includes recent runtime effects and clipped summaries.
- Project snapshot and memory systems exist.

Missing proof:

- No task-local resume bundle that reconstructs files touched, commands run, failures, decisions, and open risks.
- No watcher-driven passive updates.
- User preference memory is not yet clearly shaping behavior.

Next action:

- Define task-local work memory and feed it into the native work session context.

## Milestone 4: True Recovery

Status: `foundation`

Evidence:

- Runtime effects persist lifecycle status.
- `mew doctor` detects incomplete runtime cycles/effects.
- `mew repair` can mark unfinished effects as `interrupted`.
- Interrupted effects receive `recovery_hint`.
- Runtime effects now record user-visible `outcome`.

Missing proof:

- No automatic resume/retry/abort/ask_user decision from interrupted effects.
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

- `uv run pytest -q` current: `464 passed, 4 subtests passed`.
- `uv run pytest -q tests/test_work_session.py` current: `26 passed`.
- `uv run pytest -q tests/test_codex_api.py tests/test_model_backends.py tests/test_work_session.py tests/test_dogfood.py::DogfoodTests::test_run_dogfood_work_session_scenario` current: `39 passed`.
- `uv run python -m compileall -q src/mew` current: pass.
- `./mew dogfood --scenario work-session --cleanup` current: pass.
- `./mew dogfood --scenario all --cleanup` current: pass, including `work-session`.
- `./mew doctor --auth auth.json` current: state/runtime/auth ok.

## Current Roadmap Focus

Milestone 2: Interactive Parity.

The next implementation should make `mew work --ai` feel closer to a live coding shell: readable diffs, streaming/progress surfaces, and cockpit commands that expose the current model turn, tool result, files touched, verification state, and next action.
