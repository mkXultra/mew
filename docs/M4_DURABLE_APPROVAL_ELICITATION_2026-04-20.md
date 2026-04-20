# M4 Durable Approval Elicitation 2026-04-20

Status: focused proof passed.

This is a narrow M4 slice for approval recovery. It makes live write approvals
durable before reading stdin, so an interrupted prompt is recoverable through
normal mew reentry surfaces.

## Behavior

When `mew work --live --prompt-approval` reaches a dry-run write/edit that
requires approval, mew now creates a `work_approval` question before displaying
the inline prompt.

The question records:

- work session id and tool call id;
- task id/title when available;
- tool/path/summary;
- approve, reject, defer, or override commands from the pending approval
  surface;
- a reminder to inspect the pending approval if the prompt was interrupted.

If stdin is interrupted or returns EOF, the question remains open. It is also
linked from outbox and attention, so `mew focus`, `mew brief`, and normal
question surfaces can recover the pending decision.

When the approval is successfully applied or rejected, the linked question is
answered. Failed or interrupted apply attempts leave the question open because
the approval still requires review.

## Validation

Focused tests:

```bash
uv run pytest --testmon -q tests/test_work_session.py -k 'prompt_approval_records_durable_question or prompt_approval_can_reject_dry_run_write_inline or prompt_approval_answers_question_after_apply or approval_handles_missing_apply_tool_after_execution or approval_interrupt_marks_apply_indeterminate'
uv run --with ruff ruff check src/mew/commands.py tests/test_work_session.py
```

Result:

- `test_work_live_prompt_approval_records_durable_question_when_unanswered`
  proves EOF at the prompt leaves an open `work_approval` question with
  approve/reject commands while the work session remains `awaiting_approval`.
- `test_work_live_prompt_approval_can_reject_dry_run_write_inline` now proves
  inline rejection answers the linked approval question.
- `test_work_live_prompt_approval_answers_question_after_apply` proves a
  successful inline approval answers the linked approval question.
- existing indeterminate-approval tests still prove interrupted or stale apply
  attempts do not incorrectly resolve the pending approval.

## Interpretation

This does not make approvals autonomous. It makes the human decision request
recoverable after a crash, terminal close, or context compression. That directly
supports M4's requirement that a crashed runtime can restart and make a safe
next move without manually reconstructing what question was being asked.
