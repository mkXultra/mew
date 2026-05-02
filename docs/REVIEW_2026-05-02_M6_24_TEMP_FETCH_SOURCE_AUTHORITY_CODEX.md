# Review 2026-05-02 - M6.24 Temp-Fetch Source Authority

Reviewer: `codex-ultra`

Session: `019de79b-b8cb-7d03-b2f6-f28536cbef43`

Scope: current uncommitted temp-fetch source-authority repair in
`src/mew/long_build_substrate.py` and `tests/test_long_build_substrate.py`.

## Round 1

Status: `REQUEST_CHANGES`

Findings:

1. `_segment_authoritative_archive_fetch_paths()` scanned all URLs in the
   resolved curl/wget segment, so authoritative URLs in option values such as
   headers, referer, user-agent, or data could make a mirror download look
   authoritative.
2. Temp fetch correlation accepted any matching `mv` anywhere in the command,
   not necessarily an ordered `fetch -> mv` sequence.
3. Non-terminal structural completion could satisfy source authority when a
   failed fetch had clipped/redirected stderr and a later stale archive readback
   existed.

## Fixes Reviewed

- URL authority now uses fetch-argument extraction that skips curl/wget option
  values.
- Temp archive promotion now requires ordered pending-temp fetch followed by an
  exact-source `mv` to the final source archive path.
- Non-terminal structural acquisition completion now requires prior final
  archive absence or explicit pre-fetch final archive removal.
- New regressions cover header-only URLs, pre-fetch move ordering, visible
  failed fetch, and clipped failed fetch with stale readback.

## Round 2

Status: `APPROVE`

No blocking findings.

Reviewer confirmation:

- authoritative URL option-value false positives are addressed;
- temp fetch correlation is ordered;
- clipped failed fetch plus stale readback remains rejected unless the final
  archive was proven absent or explicitly removed before fetch.

Reviewer also reported a full reducer test-file pass:

```text
uv run pytest -q tests/test_long_build_substrate.py
228 passed, 11 deselected
```
