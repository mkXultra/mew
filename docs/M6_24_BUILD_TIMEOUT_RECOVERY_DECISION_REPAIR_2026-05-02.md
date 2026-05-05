# M6.24 Build-Timeout Recovery Decision Repair

Date: 2026-05-02 JST

## Trigger

Same-shape `compile-compcert` speed_1 after the temp-fetch source-authority
repair failed with reward `0.0` and no runner errors:

- job:
  `mew-m6-24-temp-fetch-source-authority-compile-compcert-1attempt-20260502-1653`
- runtime: `30m28s`
- source authority: satisfied
- configure/dependency generation: reached
- final explicit build: `make -j"$(nproc)" ccomp`
- failure: process group timeout during `ccomp`, before the later `make install`
  and smoke proof lines were reached

The long-build reducer reported `target_selection_overbroad` from the later
`make install` text in the same shell command. That was stale: the command had
already selected the explicit target `ccomp`, and the `make install` segment was
not reached before timeout.

## Repair

Generic repair name:
`long_dependency_build_timeout_recovery_decision_context_contract`.

Changes:

- `untargeted_full_project_build_for_specific_artifact` is suppressed only when
  it comes from the same command evidence as the latest `build_timeout` and the
  blocker excerpt is the unreached later `make install` segment. This prevents
  unreached install text from overriding the actual reached execution state.
- Unrelated blockers and real same-call overbroad builds remain active. A
  source-authority blocker still drives `current_failure`, and a timed-out
  `make all`/full-project build still reports target-selection overbreadth.
- `compact_recovery` now has a real context cap:
  - tighter run/read/list/model-turn text limits
  - compacted `long_build_state`
  - no older `session_knowledge`
  - recovery-mode recent read windows
  - a small `CompactRecoveryLaneBase` instead of the full implementation base
    and continuation sections

Replay-style measurement on the latest report:

- previous compact-recovery prompt: about `124k` chars
- repaired compact-recovery prompt: about `46.5k` chars
- repaired work-session context: about `24.9k` chars

## Validation

Passed:

- `uv run ruff check src/mew/long_build_substrate.py src/mew/work_loop.py tests/test_long_build_substrate.py tests/test_work_session.py`
- `uv run pytest tests/test_long_build_substrate.py tests/test_work_session.py::WorkSessionTests::test_compact_recovery_context_hard_caps_long_build_payloads tests/test_work_session.py::WorkSessionTests::test_plan_work_model_turn_uses_compact_recovery_under_wall_timeout_ceiling tests/test_work_session.py::WorkSessionTests::test_work_model_context_uses_compact_recovery_after_timeout_with_pending_steer -q`

New tests pin:

- mixed `make depend; make explicit-target; make install; smoke` timeout
  reports `build_timeout`, not target-selection overbreadth
- same-evidence unreached install blocker is not active after build timeout
- compact recovery context stays within the compact context budget and preserves
  `long_build_state.current_failure` / `recovery_decision`

## Next Action

After review, run one same-shape `compile-compcert` speed_1.

Close only if:

- Harbor reward is `1.0`
- runner errors are `0`
- `mew work` exits `0`
- `/tmp/CompCert/ccomp` is invokable
- default smoke passes
- source authority is satisfied
- no stale `current_failure` or strategy blocker remains
