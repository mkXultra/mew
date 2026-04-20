# M4 Command Review Recovery 2026-04-20

Status: focused tests passed.

This is a conservative M4 shell-recovery slice. It does not retry shell
commands. It makes failed `run_command` calls first-class recovery-plan review
items so a resident model does not have to infer command risk from the generic
failure list.

## Behavior

- failed `run_command` calls now enter `recovery_plan.items` as:
  - `action=needs_user_review`
  - `safety=command`
  - `effect_classification=action_committed`
- the recovery item carries the recorded command, review hint, and review steps;
- the recovery item also carries `cwd`, `exit_code`, and captured
  `stdout_tail`/`stderr_tail` when available, so JSON consumers can review the
  selected shell recovery item without separately joining against the command
  pane;
- the failure list still keeps `recorded_output_review` so stdout/stderr remain
  visible before any rerun;
- the shared recovery next action now says to review side-effecting work, not
  only interrupted side-effecting work.

## Validation

```bash
uv run pytest -q tests/test_work_session.py -k 'failed_command or side_effect_review_context or recovery_suggestions_prefer_side_effect_review'
uv run pytest --testmon -q tests/test_work_session.py -k 'recorded_output_review_after_failed_command or side_effect_review_context'
```

Result:

- `3 passed`
- `2 passed`

## Interpretation

This keeps shell recovery intentionally manual while making the safe next move
visible from the same recovery-plan surface used by passive/native recovery.
Automatic shell retry remains deferred until mew has a deterministic validator
for idempotence and world state.
