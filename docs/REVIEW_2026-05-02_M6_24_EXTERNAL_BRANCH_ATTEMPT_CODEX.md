# Review: M6.24 External-Branch Attempt Repair - codex-ultra

Reviewer: `codex-ultra`

Session: `019de766-9116-7671-b95c-dfa85da2b005`

Status: `APPROVE`

## Initial Review

The first review returned `REQUEST_CHANGES` with two blockers:

1. The detector missed the ordering where dependency/API mismatch happens
   before later help output exposes the external/prebuilt branch.
2. The standalone `api library` marker could turn successful `./configure
   --help` text into a false positive.

## Resolution

- Mismatch state is now tracked independently of external-help ordering.
- API-library text is scoped to failed/error calls through a more specific
  regex instead of a standalone marker.
- Regression tests cover mismatch-before-help and successful help text that
  mentions `API library`.
- `long_build_substrate.py` maps
  `source_toolchain_before_external_branch_attempt` to
  `dependency_strategy_unresolved` and gives it a specific clear condition.

## Final Reviewer Result

`STATUS: APPROVE`

No blocking findings in the current diff.

Reviewer-reported tests:

- `uv run pytest --no-testmon tests/test_work_session.py -k 'source_toolchain_before_external_branch_attempt or mismatch_precedes_external_help or successful_help_api_library_text or source_toolchain_after_external_branch_attempt or source_toolchain_before_mismatch or external_branch_help_probe' -q`
  - `8 passed`
- `uv run pytest --no-testmon tests/test_long_build_substrate.py tests/test_work_session.py -q`
  - `1101 passed, 1 warning`
- `uv run ruff check src/mew/work_session.py src/mew/work_loop.py src/mew/long_build_substrate.py tests/test_work_session.py`
  - passed
- `git diff --check`
  - passed
