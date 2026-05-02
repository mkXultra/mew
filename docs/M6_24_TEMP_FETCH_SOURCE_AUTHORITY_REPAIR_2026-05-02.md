# M6.24 Temp-Fetch Source Authority Repair - 2026-05-02

## Trigger

Same-shape `compile-compcert` speed rerun after the external-branch attempt
repair:

- Job: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-external-branch-attempt-compile-compcert-1attempt-20260502-1552/result.json`
- Trial: `compile-compcert__KZaLSBp`
- Harbor reward: `1.0`
- Runner errors: `0`
- Runtime: about `25m39s`
- `mew-report.work_exit_code`: `0`

The external verifier passed all checks and `mew work` exited cleanly. Internal
closeout still left `source_authority=unknown`.

## Root Cause

The successful run fetched the authoritative source archive to a temporary path,
moved it to the final saved archive path, then later proved the saved archive
identity near final artifact/default-smoke proof:

```text
curl -fL --retry 3 -o "$ARCH.tmp" "$URL"
mv "$ARCH.tmp" "$ARCH"
...
sha256sum /tmp/compcert-3.13.1-src.tar.gz
tar -tzf /tmp/compcert-3.13.1-src.tar.gz CompCert-3.13.1/configure CompCert-3.13.1/Makefile
```

The reducer already recognized direct final-path archive fetches and some
post-loop validated fetches, but did not correlate this temp-fetch/move pattern
with the later saved archive readback. The source acquisition output was also
clipped by later build output, so the live report did not retain the original
fetch-time hash/readback lines.

## Repair

- Resolve simple shell assignments for source archive fetch, hash, validation,
  extraction, and command-substitution validation paths.
- Recognize authoritative `curl`/`wget` fetches to temp paths only when the
  actual fetch URL argument is authoritative.
- Promote a temp fetch to the final source archive path only through an ordered
  later `mv <temp> <final>` segment.
- Correlate a strict authoritative acquisition with a later top-level saved
  archive hash/list readback.
- For non-terminal acquisition commands with clipped output, require either:
  - prior evidence that the final archive path was absent, or
  - explicit pre-fetch removal of the final archive path.
- Keep assertion-only `source_url=` insufficient.
- Reject stale archive false positives:
  - failed temp fetch with visible failure output,
  - failed temp fetch with clipped/redirected failure output,
  - authoritative URL only in a curl header/referer/data option,
  - `mv "$ARCH.tmp" "$ARCH"` before the temp fetch.

## Validation

- Live report replay:
  - `mew-m6-24-external-branch-attempt-compile-compcert-1attempt-20260502-1552`
  - after repair: `source_authority=satisfied`, `target_built=satisfied`,
    `default_smoke=satisfied`, `status=complete`, no `current_failure`, no
    `strategy_blockers`.
- Focused temp-fetch/source-authority subset:
  - `uv run pytest -q tests/test_long_build_substrate.py -k 'direct_temp_fetch or header_only_authoritative_url or prefetch_move_before_temp_download or source_authority_correlates_direct_temp_fetch_move' --no-testmon`
  - `4 passed, 235 deselected`
- Source-authority/source-acquisition subset:
  - `uv run pytest -q tests/test_long_build_substrate.py -k 'source_authority or saved_archive or archive_readback or source_acquisition' --no-testmon`
  - `162 passed, 77 deselected`
- Combined long-build/work-session/acceptance subset:
  - `uv run pytest -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py -k 'long_build or long_dependency or source_authority or default_smoke' --no-testmon`
  - `276 passed, 962 deselected, 22 subtests`
- Full long-build substrate tests:
  - `uv run pytest -q tests/test_long_build_substrate.py --no-testmon`
  - `239 passed`
- Ruff:
  - `uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py`
  - passed
- Diff check:
  - `git diff --check`
  - passed
- Gap ledger JSON parse:
  - passed

## Review

`codex-ultra` session `019de79b-b8cb-7d03-b2f6-f28536cbef43` first returned
`REQUEST_CHANGES` for:

- authoritative URLs in curl/wget option values such as headers, referer, or
  data values;
- unordered temp-fetch/move correlation;
- clipped failed fetch output followed by stale archive readback.

The repair was hardened with regressions for all three classes. The same
session then returned `STATUS: APPROVE`.

Review record:

- `docs/REVIEW_2026-05-02_M6_24_TEMP_FETCH_SOURCE_AUTHORITY_CODEX.md`

## Next

Commit the repair, then rerun one same-shape `compile-compcert` speed_1.
Do not run proof_5 or broad measurement until the live run records:

- Harbor reward `1.0`,
- runner errors `0`,
- command transcript exit `0`,
- `mew-report.work_exit_code=0`,
- `source_authority=satisfied`,
- no stale `current_failure`,
- no active stale strategy blockers.
