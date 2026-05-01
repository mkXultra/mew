# M6.24 Long-Build Substrate Phase 3 - RecoveryDecision

Date: 2026-05-02 JST

## Scope

Implemented Phase 3 of `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`.

Phase 3 adds a typed `RecoveryDecision` for the narrow approved subset:

- `artifact_missing_or_unproven`
- `build_timeout`
- `runtime_link_failed`
- `runtime_default_path_unproven`
- `runtime_install_before_build`
- `build_system_target_surface_invalid`
- `budget_reserve_violation`

The decision is derived from `LongBuildState`, command evidence, strategy blockers,
and wall-budget facts. It chooses one next recovery action and clear condition; it
does not decide task completion and does not handle model-format recovery.

## Changes

- `src/mew/long_build_substrate.py`
  - derives `RecoveryDecision` during `reduce_long_build_state()`;
  - maps default runtime link failures to `runtime_link_failed`;
  - maps late branch/budget exhaustion to `budget_reserve_violation`;
  - suppresses stale build-timeout failures after later artifact/default-smoke
    success;
  - serializes `suggested_next` only when there is a current failure without a
    recovery decision.
- `src/mew/work_session.py`
  - renders compact `long_build_recovery_*` lines from `RecoveryDecision`;
  - suppresses old long `long_build_next` paragraphs when typed recovery state is
    available.
- `tests/test_long_build_substrate.py`
  - adds transfer fixtures for non-CompCert CLI/toolchain/runtime target shapes;
  - pins stale-diagnostic clearing after later success.
- `tests/test_work_session.py`
  - pins resume rendering for recovery decisions;
  - pins stale native command timeout clearing after later artifact proof;
  - pins prompt-section metrics so dynamic long-build state does not grow the
    static `LongDependencyProfile`.

## Validation

- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py`
  - `1036 passed, 1 warning, 67 subtests passed`
- `uv run ruff check src/mew/long_build_substrate.py src/mew/work_session.py tests/test_long_build_substrate.py tests/test_work_session.py`
  - passed
- `git diff --check`
  - passed

## Review

codex-ultra review session `019de40c-42a8-71c1-955b-07022e84f1ec` returned
`PASS` after four rounds. Required changes fixed before PASS:

- stale runtime/build diagnostics surviving later successful proof;
- finish-policy wording leaking into `RecoveryDecision`;
- missing explicit coverage for `budget_reserve_violation` and
  `runtime_install_before_build`;
- stale `incomplete_reason=tool_timeout` and old `long_build_next` rendering
  after recovery was cleared.

## Measurement Gate

Do not resume broad measurement yet.

Same-shape `compile-compcert` speed_1 is technically allowed after Phase 3 by
the design, but Phase 4 changes recovery-budget enforcement. Because M6.24's
current long-build gap repeatedly involves wall/recovery budget behavior, the
selected next action is Phase 4 before measurement.

