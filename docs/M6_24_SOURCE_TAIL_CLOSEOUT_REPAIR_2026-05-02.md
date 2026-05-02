# M6.24 Source-Tail Closeout Repair - 2026-05-02

## Trigger

Same-shape `compile-compcert` speed rerun:

- Job: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-tail-closeout-compile-compcert-1attempt-20260502-1347/result.json`
- Harbor reward: `1.0`
- Runner exceptions: `0`
- Runtime: `23m44s`
- Command transcript exit: `0`
- `mew-report.work_exit_code`: `0`

External task success was clean, but internal long-build closeout stayed blocked:

- `source_authority=unknown`
- `default_smoke=unknown`
- `current_failure=target_selection_overbroad`
- stale blockers included `make install` and earlier dependency/toolchain failures

## Root Cause

The reducer was still treating two historical facts as active failures after the final successful proof:

1. The final command first hit `cannot find -lcompcert`, repaired the runtime with `make -C runtime all` and `make install`, then reran a default compile/link/run smoke successfully.
2. The same final command proved the saved source archive with `sha256sum` plus `tar -tzf`, but listed specific archive members (`configure`, `Makefile`) instead of a bare top-level root line.

The external verifier correctly passed. The internal reducer failed to recognize the final command as complete evidence.

## Repair

- Suppress `runtime_link_failed` diagnostics when the same terminal-success command contains a valid final default compile/link smoke for the required artifact.
- Accept terminal-success saved source archive identity readback when:
  - the command hashes and lists the same versioned source archive path,
  - the output contains the matching archive hash,
  - the output contains either an archive root line or concrete archive member lines such as `configure` / `Makefile`,
  - the command is not hidden behind shell functions or assertion-only authority text.
- Keep local archive readback from becoming source authority by itself. It only satisfies `source_authority` when correlated with an earlier strict authoritative archive acquisition for the same versioned archive path.
- Recognize GitHub API `tarball` / `zipball` URLs and `codeload.github.com` archives as authoritative source archive URLs.
- Recognize the common `cat <<EOF > candidates` plus `while read url; curl -o "$archive" "$url"` acquisition pattern when the loop records the selected URL and the later final proof reads back the same archive path.
- After `codex-ultra` review, authoritative acquisition paths are only seeded from evidence that proves acquisition completed:
  - terminal-success evidence,
  - ordered fetch/hash/validation output, or
  - a strict post-extract progress marker emitted after the archive extraction command.
  A failed authoritative `curl` followed by later local archive readback remains `source_authority=unknown`.
- After the second `codex-ultra` review, post-extract marker completion is rejected when source-acquisition failure output is present, and only markers unique to the post-extract portion of the command can prove acquisition progress. A duplicate pre-fetch `CONFIGURE_TARGET` plus failed `curl` followed by local archive readback remains `source_authority=unknown`.

## Validation

- Focused source/default-smoke subset:
  - `uv run pytest --no-testmon -q tests/test_long_build_substrate.py -k 'source_authority or saved_archive or while_read or runtime_repair_and_saved_archive_readback or default_smoke_allows_later_errexit_disable or reducer_clears_runtime_install_blocker'`
  - `159 passed, 75 deselected`
- Long-build substrate:
  - `uv run pytest --no-testmon -q tests/test_long_build_substrate.py`
  - `234 passed`
- Combined regression:
  - `uv run pytest --no-testmon -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py`
  - `1229 passed, 1 warning, 67 subtests`
- Ruff:
  - `uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py`
  - passed
- JSONL parse:
  - `proof-artifacts/m6_24_gap_ledger.jsonl`
  - `142 jsonl lines`
- Diff check:
  - `git diff --check`
  - passed

Local replay of the live `20260502-1347` report with the patched reducer now returns:

- `status=complete`
- `source_authority=satisfied`
- `default_smoke=satisfied`
- `current_failure=null`
- `strategy_blockers=[]`

## Review

`codex-ultra` session `019de722-3e81-70d0-ab40-c764397a9785` approved after two false-positive hardening rounds.

- Review record: `docs/REVIEW_2026-05-02_M6_24_SOURCE_TAIL_CLOSEOUT_CODEX.md`

## Next

Rerun one same-shape `compile-compcert` speed_1 before proof_5 or broad measurement.
