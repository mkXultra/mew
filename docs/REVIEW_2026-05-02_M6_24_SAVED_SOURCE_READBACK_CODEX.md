# M6.24 Saved Source Readback Review - 2026-05-02

Reviewer: `codex-ultra`

Session: `019de6a8-c827-75f3-974b-67a08d05b5b2`

## Scope

Review `source_authority` recognition for saved source readback evidence after
the `compile-compcert` clean-closeout speed run passed externally but kept
`source_authority=unknown` internally.

The reviewed contract:

- saved authority-page or tag metadata must be read back
- archive hash and archive listing must be real commands over the same archive
- readbacks must be top-level required commands
- hidden, optional, spoofed, guarded, redirected, backgrounded, or mismatched
  readbacks must not satisfy `source_authority`

## Review Rounds

The reviewer first required hardening for several spoof paths:

- guarded `if` readbacks with fake shell xtrace
- masked `|| true` hash/list commands
- tag JSON readback false negatives
- skipped `if`/`while` blocks with printed hash/root output
- uncalled shell functions
- direct and pipeline redirection
- `exec` stdout redirection, including restore-then-redirect and `1<>`
- redirected brace/subshell compound commands, including `time` variants
- backgrounded hash/list readbacks

All required cases were converted into negative tests.

## Final Status

`STATUS: APPROVE`

Final validation:

- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py -k 'saved_authority_page or source_authority'`
  - `154 passed, 74 deselected`
- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py`
  - `1223 passed, 1 warning, 67 subtests passed`
- `uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py`
  - passed
- `git diff --check`
  - passed
- `jq -c . proof-artifacts/m6_24_gap_ledger.jsonl`
  - passed

## Next Action

Run one same-shape `compile-compcert` speed_1. Do not run proof_5 or broad
measurement until the live run records all closeout fields:

- Harbor reward `1.0`
- runner errors `0`
- command transcript exit `0`
- `mew-report.work_exit_code=0`
- `source_authority=satisfied`
- `current_failure=null`
- `strategy_blockers=[]`
