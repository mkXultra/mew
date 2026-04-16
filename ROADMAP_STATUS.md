# Mew Roadmap Status

Last updated: 2026-04-16

This file tracks progress against `ROADMAP.md`. Keep it evidence-based and conservative.

## Summary

| Milestone | Status | Short Assessment |
|---|---|---|
| 1. Native Hands | `in_progress` | Native work sessions can run and journal read/search/glob/test/shell tools; write/edit/model tool loop is still missing. |
| 2. Interactive Parity | `foundation` | `mew chat` exists and gained cockpit commands, but it is not yet a Claude Code-quality live coding UI. |
| 3. Persistent Advantage | `foundation` | Durable state, memory, context, and runtime effects exist; automatic task resume context is still incomplete. |
| 4. True Recovery | `foundation` | `doctor`, `repair`, runtime effect journal, `recovery_hint`, and `outcome` exist; automatic safe resume is not implemented. |
| 5. Self-Improving Mew | `foundation` | Self-improvement and dogfood entry points exist; closed-loop self-improvement is not yet reliable. |

## Milestone 1: Native Hands

Status: `in_progress`

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
- `/work-session` in chat can start, show, and close native work sessions.
- `dogfood --scenario work-session` exercises session creation, `read_file`, `glob`, `run_tests`, and workbench journal visibility.

Missing proof:

- No model tool loop where read/edit/test results flow back into the same model work session.
- No native edit/write tools inside work sessions yet.
- Real coding still leans on external agent dispatch for serious work.

Next action:

- Add edit/write-capable work-session tools behind explicit gates, then feed tool results into a resident model work loop.

## Milestone 2: Interactive Parity

Status: `foundation`

Evidence:

- `mew chat` exists.
- Chat can inspect focus, status, workbench, agents, verification, writes, thoughts, runtime effects, doctor, and repair.

Missing proof:

- No streaming model output.
- No streaming command output.
- No integrated diff approval flow.
- No live coding work session UX.

Next action:

- After Milestone 1's first native work loop exists, add chat commands that expose current work session state and tool results.

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

- `uv run pytest -q` current: `444 passed, 4 subtests passed`.
- `./mew dogfood --scenario work-session --cleanup` current: pass.
- `./mew dogfood --scenario all --cleanup` current: pass, including `work-session`.
- `./mew doctor --auth auth.json` current: state/runtime/auth ok.

## Current Roadmap Focus

Milestone 1: Native Hands.

The next implementation should not add more roadmap or memory surface unless it directly helps build or validate the first native work loop.
