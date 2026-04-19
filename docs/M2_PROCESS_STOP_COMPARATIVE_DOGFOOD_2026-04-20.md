# M2 Process-Stop Comparative Dogfood - 2026-04-20

Purpose: test a stricter M2 interruption path where the live `mew work --follow` process is stopped with Ctrl-C, then the task is resumed and completed without rebriefing the task from scratch.

Base commit: `c1f7afb Prove M2 interruption dogfood gate`

## Task

Add a new M2 comparative task shape named `process_stop`.

Required surfaces:

- `src/mew/dogfood.py`
- `tests/test_dogfood.py`

## Mew Leg

Workspace: `/tmp/mew-m2-process-stop-mew`

Result: completed across two work sessions for the same task.

Session `#1`:

- started the task and inspected the task-shape/test surfaces
- was interrupted with Ctrl-C during step 3
- recorded `stop=user_interrupt`
- preserved `last_user_interrupt`, an interrupted model turn, working memory, pending paired-test steer, recovery plan, and `9/9 strong` continuity
- later hit a real verification/rollback failure from applying test-only edits before source support
- closed with a replan note rather than completing the task

Session `#2`:

- started from the same task without a fresh task rebrief
- recovered from the partial test edit and task notes
- applied the remaining test edit with deferred verification
- added `process_stop` to `M2_COMPARATIVE_TASK_SHAPES`
- passed focused and broad verification

Verification:

- `uv run pytest -q tests/test_dogfood.py -k m2_task_shape` passed
- `uv run python -m unittest tests.test_dogfood` passed

Important behavior:

- The actual process stop and the final verification landed in different work sessions.
- A single-session M2 gate could not prove the run:
  - session `#1` preserved interruption/risk but had no passing verification
  - session `#2` had passing verification but no interruption/risk
- `mew dogfood --scenario m2-comparative --mew-session-id task:<id>` now evaluates a task-level chain of work sessions.

Mew-side task-chain gate:

- `status`: `proved`
- `evidence_mode`: `task_chain`
- `work_session_ids`: `[1, 2]`
- `risk_session_ids`: `[1]`
- `verification_session_ids`: `[2]`
- `changed_or_pending_work`: true
- `risk_or_interruption_preserved`: true
- `runnable_next_action`: true
- `continuity_usable`: true
- `verification_after_resume_candidate`: true

## Fresh CLI Leg

Workspace: `/tmp/mew-m2-process-stop-fresh`

Runner: `codex-ultra` through `acm run`

Result: completed.

Evidence:

- changed `src/mew/dogfood.py`
- changed `tests/test_dogfood.py`
- wrote `/tmp/mew-m2-process-stop-fresh/fresh-cli-report.json`
- verification passed:
  - `uv run pytest -q tests/test_dogfood.py -k m2_task_shape`
  - `uv run pytest -q tests/test_dogfood.py -k "m2_comparative or m2_task_shape"`

Fresh-side report judged:

- `status`: `completed`
- `preference_signal`: `inconclusive`
- `interruption_resume_gate`: `unknown`
- Reason: the fresh run was not interrupted.

## Combined Result

Generated combined protocol:

- JSON: `/tmp/mew-m2-process-stop-combined/.mew/dogfood/m2-comparative-protocol.json`
- Markdown: `/tmp/mew-m2-process-stop-combined/.mew/dogfood/m2-comparative-protocol.md`

Combined status:

- `inconclusive`

Important protocol facts:

- mew interruption gate: `proved`
- mew evidence mode: `task_chain`
- fresh CLI interruption gate: `unknown`
- resident preference: `inconclusive`

## Product Findings

What worked:

- Ctrl-C was captured as a user interruption with useful reentry controls.
- The resume bundle preserved enough state to continue.
- The task could complete after starting a new work session for the same task.
- Task-chain evidence now lets M2 dogfood evaluate realistic stop/resume workflows.

What still felt weak:

- The resident closed session `#1` with a replan instead of continuing to completion.
- Multi-edit test-first flows still require human use of `--defer-verify` to avoid test-only rollback before the source companion lands.
- The comparison still does not prove mew is preferable to a mature fresh coding CLI, because the fresh side was not interrupted and remained lower ceremony for the narrow code change.

## Decision

Record this as the first process-stop M2 comparative run where the mew-side gate is proved via task-chain evidence.

Do not close M2 from this alone. The next high-value M2 work should reduce the paired approval / deferred verification ceremony or run a matching interrupted fresh-CLI comparison.
