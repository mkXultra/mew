# M6.24 Authority Page Source Signal Repair

Recorded: 2026-05-02 08:02 JST

## Decision

The same-shape `compile-compcert` speed rerun after commit `7842d25` passed
the external Harbor verifier and exited cleanly, but the internal
`source_authority` stage remained `unknown`. Treat this as a generic
source-authority evidence reduction defect, not as permission to move to
proof_5.

## Evidence

- Job:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-clean-closeout-source-authority-compile-compcert-1attempt-20260502-0730`
- Harbor summary:
  - `n_trials=1`
  - `n_errors=0`
  - reward mean `1.0`
  - trial `compile-compcert__dMpv8Cd`
- Internal transcript:
  - command transcript `exit_code=0`
  - `timed_out=false`
  - `mew-report.work_exit_code=0`
- Internal state before repair:
  - `current_failure=null`
  - `strategy_blockers=[]`
  - `target_built=satisfied`
  - `default_smoke=satisfied`
  - `source_authority=unknown`

The run used non-Python authority-producing source acquisition and final proof:

- installed `curl`
- fetched candidate authority pages and archive URLs
- selected a versioned CompCert release archive
- recorded archive SHA-256 and archive root
- later validated a saved authority page and the archive identity in the final
  consolidated proof

The reducer did not convert the final saved-authority-page proof into a
`source_authority` signal.

## Root Cause

`_source_authority_signal()` only recognized direct source acquisition output
such as `authority_archive_url=...` and package metadata output. It did not
recognize the safe split pattern used by long builds:

1. fetch source and authority pages during setup
2. build and repair runtime/library paths
3. in the final proof, verify the saved authority page, archive hash, archive
   root, artifact, and default runtime smoke together

Because the direct acquisition output can be clipped out of command head/tail,
the final proof must be able to carry the source-authority signal when it
contains non-spoofed saved authority-page readback plus archive identity.

## Repair

Implemented in this slice:

- `src/mew/long_build_substrate.py`
  - recognizes `authority_page_saved=` / `authority_page_fetched=` output only
    when paired with `archive_sha256=` and `archive_root=`
  - requires active `errexit`
  - rejects Python remote source-acquisition paths for this signal
  - requires either non-Python remote source acquisition in the command or
    readback of a saved authority page with `grep`
- `tests/test_long_build_substrate.py`
  - accepts saved authority-page readback plus archive identity
  - rejects authority-page output without archive identity
  - rejects echoed authority-page output without readback or fetch
  - rejects saved authority-page output when the archive came from Python
    remote acquisition, including aliased `urlretrieve`, versioned
    `python3.x -c`, keyword URL calls such as `requests.get(url=...)`, and
    URL variables passed into Python remote fetch calls

## Validation

- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py`
  - `156 passed`
- `uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py`
  - passed
- Local replay of the `20260502-0730` report after this repair now reduces to:
  - `status=complete`
  - `source_authority=satisfied`
  - `target_built=satisfied`
  - `default_smoke=satisfied`
  - `current_failure=null`
  - `strategy_blockers=[]`

## Next Action

Run code review, commit this repair, then rerun one same-shape
`compile-compcert` speed_1. Do not run proof_5 or broad measurement until a
live run, not just local replay, records:

- Harbor reward `1.0`
- runner errors `0`
- command transcript exit `0`
- `mew-report.work_exit_code=0`
- `source_authority=satisfied`
- no stale `current_failure`
- no active stale strategy blockers
