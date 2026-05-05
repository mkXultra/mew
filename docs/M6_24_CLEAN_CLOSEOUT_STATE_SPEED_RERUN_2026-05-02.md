# M6.24 Clean Closeout State Speed Rerun

Recorded: 2026-05-02 07:12 JST

## Decision

The same-shape `compile-compcert` speed rerun passed the external Harbor
verifier but did not satisfy the internal clean-closeout gate. Treat this as a
generic long-build reducer / source-acquisition closeout defect, not as proof
that broad measurement or proof_5 may resume.

## Evidence

- Job:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-clean-closeout-state-compile-compcert-1attempt-retry3-20260502-0627`
- Harbor summary:
  - `n_trials=1`
  - `n_errors=0`
  - reward mean `1.0`
  - trial `compile-compcert__RvddtyJ`
- External verifier:
  - `test_compcert_exists_and_executable`: passed
  - `test_compcert_valid_and_functional`: passed
  - `test_compcert_rejects_unsupported_feature`: passed
- Internal command transcript:
  - `exit_code=1`
  - `timed_out=false`
  - `timeout_seconds=1800`
- Internal state before repair:
  - final artifact and runtime proof existed in the transcript
  - `long_build_state.current_failure` still pointed at stale strategy blockers
  - source authority remained untrusted because the run used Python heredoc
    transport for archive fetch

The earlier retry setup attempts in the same series failed before a valid
trial because the Harbor container lacked `python` / `python3`, then pip hit
Ubuntu's externally-managed Python guard. Those attempts are harness setup
failures and are not score evidence.

## Root Cause

The final terminal proof was real but the internal reducer over-rejected it:

- artifact proof was discarded when strict proof commands also printed
  status labels such as `artifact_exists=true ...`
- default-smoke proof was discarded when a later metadata pipeline ran under
  `set -euo pipefail`
- `set -euo pipefail` was not recognized as enabling `pipefail`
- non-source historical blockers such as package/toolchain mismatch stayed
  active even after target artifact and default runtime proof were satisfied
- source authority did not close because the model used Python download
  snippets; current policy intentionally does not trust those as
  authority-producing source acquisition

## Repair

Implemented in this slice:

- `src/mew/acceptance_evidence.py`
  - spoof-only echo/printf artifact output is still rejected
  - strict artifact proof plus harmless status labels is accepted
- `src/mew/long_build_substrate.py`
  - `set -euo pipefail` counts as active `pipefail`
  - later metadata pipelines are allowed only when `errexit` and `pipefail`
    are both active
  - non-source strategy blockers clear after target artifact and required
    runtime/default-smoke proof
  - later diagnostic failures surface as the current failure instead of being
    masked by stale non-source blockers
  - true source-authority blockers remain explicit
- `src/mew/work_loop.py`
  - `SourceAcquisitionProfile` now tells the model to use non-Python fetch
    tools such as `curl`, `wget`, `gh`, or `git` for authority-producing
    source acquisition, and to install `curl` or `wget` when absent

## Validation

- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py`
  - `147 passed`
- `uv run pytest --no-testmon -q tests/test_work_session.py`
  - `863 passed`, one fork deprecation warning, `67 subtests passed`
- `uv run pytest --no-testmon -q tests/test_acceptance.py`
  - `132 passed`
- `uv run ruff check src/mew/acceptance_evidence.py src/mew/long_build_substrate.py src/mew/work_loop.py tests/test_long_build_substrate.py tests/test_work_session.py`
  - passed
- `git diff --check`
  - passed
- Local replay of the failed retry3 report after this repair now reduces to:
  - `current_failure=null`
  - `strategy_blockers=[]`
  - `target_built=satisfied`
  - `default_smoke=satisfied`
  - `source_authority=unknown`
- Combined validation after reviewer-required hardening:
  - `uv run pytest --no-testmon -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py`
  - `1142 passed`, one fork deprecation warning, `67 subtests passed`
- codex-ultra final review:
  - `docs/REVIEW_2026-05-02_M6_24_CLEAN_CLOSEOUT_SOURCE_AUTHORITY_CODEX.md`
  - `APPROVE`

## Next Action

Run one same-shape `compile-compcert` speed_1 again. The next run must use
non-Python authority-producing source acquisition and must satisfy all clean
closeout gates before proof_5 or broad measurement:

- Harbor reward `1.0`
- runner errors `0`
- command transcript exit `0`
- `mew-report` work exit `0`
- no stale `resume.long_build_state.current_failure`
- no active stale resolved strategy blockers
- `source_authority=satisfied`
