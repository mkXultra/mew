# M6.24 Long-Build Substrate Phase 4

Date: 2026-05-02 JST

## Scope

Phase 4 replaces the old marker-based long-build recovery reserve detector with
contract/state/recovery based budget enforcement.

Implemented:

- `work_tool_recovery_reserve_seconds()` now derives a `LongBuildContract` from
  `work_session.resume.long_build_state` or, for first commands, from the task's
  long-build contract inputs.
- Planned command budget policy uses
  `planned_long_build_command_stage()` from `long_build_substrate.py`, so the
  same stage classifier is used for planned commands and recorded
  `CommandEvidence`.
- `RecoveryDecision.budget.may_spend_reserve` can spend the reserve only when
  the planned command stage matches the decision's `allowed_next_action`.
- Active recovery decisions that do not allow the planned stage preserve the
  long-build reserve, including `block_for_budget` and unrelated long commands.

## Important Boundaries

This phase does not run `compile-compcert` measurement. It only makes the wall
budget decision surface match the Phase 2/3 typed substrate.

Provider-specific prompt cache transport and broader benchmark measurement stay
outside this phase.

## Validation

Passed:

- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py ... wall budget/recovery tests`
  - 64 passed
- `uv run ruff check src/mew/commands.py src/mew/long_build_substrate.py tests/test_work_session.py`
- `git diff --check`

codex-ultra review session:

- `019de42b-0c04-7010-b73e-19f41071fbc1`
- Initial review required changes for over-broad reserve spending.
- Second review required the `build_system_target_surface_probe` alias to accept
  final-smoke/artifact-proof stages.
- Final review returned `STATUS: PASS`.

## Next Action

Run one same-shape `compile-compcert` speed_1 with refreshable
`~/.codex/auth.json` before proof_5 or broad measurement.
