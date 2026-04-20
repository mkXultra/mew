# M4 Runtime Effect Recovery Decision 2026-04-20

Status: unit proof passed.

This is a narrow M4 slice for runtime-effect recovery. It does not retry runtime
effects yet. It upgrades `mew repair` from a string-only `recovery_hint` to a
structured recovery decision.

## Behavior

When `mew repair` marks an incomplete runtime effect as `interrupted`, the
effect and repair record now include `recovery_decision`.

Current classifications:

- pre-commit statuses (`planning`, `planned`, `precomputing`, `precomputed`)
  become `rerun_event` with `effect_classification=no_action_committed` and
  `safety=safe_to_replan`.
- `committing` effects with `write_run_ids` become `review_writes` with
  `effect_classification=write_may_have_started`.
- `committing` effects with `verification_run_ids` become
  `review_verification` with `effect_classification=verification_may_have_run`.
- `committing` effects with only `action_types` become `review_actions` with
  `effect_classification=action_may_have_committed`.
- unknown commit state stays on `review_unknown_commit`.

## Validation

Focused tests:

```bash
uv run pytest --testmon -q tests/test_validation.py -k 'repair_marks_incomplete_runtime_effect_interrupted or repair_classifies_committing_runtime_write_effect'
uv run pytest --testmon -q tests/test_runtime.py -k 'startup_repairs_incomplete_effects'
```

Both passed.

## Interpretation

This connects M4's recovery language to machine-readable state. A future
runtime-effect recovery command can now select from `recovery_decision` instead
of parsing prose hints.
