# M4 Runtime Effect Recovery Decision 2026-04-20

Status: unit and dogfood proof passed.

This is a narrow M4 slice for runtime-effect recovery. It upgrades `mew repair`
from a string-only `recovery_hint` to a structured recovery decision and a
follow-up action.

## Behavior

When `mew repair` marks an incomplete runtime effect as `interrupted`, the
effect and repair record now include `recovery_decision`.

`mew brief` also surfaces recent startup-repair decisions, so a resident model
or human can see whether the repaired effect was `rerun_event` or a review path
without opening raw state.

`mew doctor` previews the same recovery decision for incomplete runtime effects
and follow-up action before repair mutates state.

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

Follow-up consumption:

- pre-commit `rerun_event` decisions requeue the original event when it had
  already been marked processed and no later terminal effect exists;
- events that are already pending stay pending and record `already_pending`;
- committing write/verification/action decisions stay on explicit review
  follow-ups, pointing to the relevant inspection command instead of retrying.

## Validation

Focused tests:

```bash
uv run pytest --testmon -q tests/test_validation.py -k 'repair_marks_incomplete_runtime_effect_interrupted or repair_classifies_committing_runtime_write_effect'
uv run pytest --testmon -q tests/test_validation.py -k 'doctor_previews_incomplete_runtime_effect_recovery'
uv run pytest --testmon -q tests/test_runtime.py -k 'startup_repairs_incomplete_effects'
```

Both passed.

Dogfood:

```bash
./mew dogfood --scenario m4-runtime-effect-recovery --workspace proof-workspace/mew-proof-m4-runtime-effect-recovery-local-20260420-followup --json
```

Result:

- status: `pass`
- checks:
  - `m4_runtime_effect_recovery_doctor_previews_decisions`
  - `m4_runtime_effect_recovery_requeues_precommit_event`
  - `m4_runtime_effect_recovery_classifies_committing_write_review`

## Interpretation

This connects M4's recovery language to machine-readable state and lets repair
consume the safest class directly: a pre-commit runtime effect can make its
original event pending again. Commit-phase effects still require explicit
review.
