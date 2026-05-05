# Review: M6.24 Stale Strategy-Blocker Clearing

Date: 2026-05-02 JST

Reviewer: codex-ultra

Session: `019de45d-0f50-7623-b441-b13158656286`

## Scope

Reviewed the uncommitted long-build substrate follow-up that clears historical
strategy blockers after final source-authority, artifact, and default-smoke
proof.

Files reviewed:

- `src/mew/long_build_substrate.py`
- `tests/test_long_build_substrate.py`

## Round 1

Status: `REQUIRED_CHANGES`

Finding:

- Direct source-authority detection accepted `local_sha256=` and `archive_top=`
  as standalone authority markers. Those prove local identity, not source
  authority, and could falsely clear `external_dependency_source_provenance_unverified`.

Required tests:

- negative local-hash-only source authority;
- negative archive-top-only source authority;
- reducer negative where artifact/default-smoke proof is not enough to clear a
  source-authority blocker without authority evidence.

## Round 2

Status: `PASS`

Reviewer result:

- Direct-source authority now requires authority-bearing markers such as
  `upstream_ref`, `upstream_ref_url`, `authority_archive_url`, or
  `matched_authority_url`.
- `local_sha256` and `archive_top` alone no longer count.
- Positive combined final proof and stale-blocker clearing remain covered.
- The new reducer negative covers the previous false-clear risk.

Reviewer validation:

- `uv run pytest --no-testmon -p no:cacheprovider tests/test_long_build_substrate.py`
  - 60 passed
- `uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py`
- `git diff --check -- src/mew/long_build_substrate.py tests/test_long_build_substrate.py`

No files modified by reviewer.
