# Review 2026-05-02: M6.24 Config/Source External Hook Evidence

Reviewer: `codex-ultra`

Session: `019de8a3-1ff6-7d90-945c-53255b9743e2`

## Initial Review

Status: `REQUEST_CHANGES`

Findings:

- Hook evidence searched command text through `_runtime_artifact_call_text()`.
  A failed/no-output grep containing literal `LIBRARY_FOO=local # external`
  could falsely create `source_toolchain_before_external_branch_attempt`.
- Assignment-style attempts such as
  `LIBRARY_FOOLIB=external ./configure ...` did not clear the blocker.
- Tests and durable evidence were missing these hardening cases.

## Fix

- External-branch hook evidence now uses observed output text and excludes shell
  xtrace stderr lines.
- Assignment-style external configure attempts clear the
  source-toolchain-before-external-branch blocker.
- Added regressions for:
  - positive configure/source-script hook evidence;
  - query-only/xtrace false positive;
  - assignment-style external attempt clear;
  - external-branch budget timeout preserving branch-attempt semantics.
- Updated durable docs and `proof-artifacts/m6_24_gap_ledger.jsonl`.

## Validation

- Focused selector:
  `8 passed, 869 deselected`
- Broader long-build/work-session/acceptance subset:
  `309 passed, 956 deselected, 22 subtests`
- `uv run ruff check src/mew/work_session.py src/mew/work_loop.py tests/test_work_session.py`
  passed.
- `jq -c . proof-artifacts/m6_24_gap_ledger.jsonl >/dev/null` passed.
- `git diff --check` passed.

## Final Review

Status: `APPROVE`

No blocking findings.

Reviewer confirmed:

- hook evidence is output-only;
- query-only/xtrace coverage is pinned;
- assignment-style attempts clear the blocker;
- durable evidence aligns with the next same-shape `speed_1` gate.
