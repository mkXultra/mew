# M6.24 Saved Source Readback Repair - 2026-05-02

## Decision

The `compile-compcert` same-shape speed rerun after commit `875fbd0`
externally passed, but the internal clean closeout gate stayed open because
`source_authority` was `unknown`.

Observed gate state:

- Harbor reward: `1.0`
- runner errors: `0`
- command transcript exit: `0`
- `mew-report.work_exit_code`: `0`
- `current_failure`: `null`
- `strategy_blockers`: `[]`
- `source_authority`: `unknown`

This is a reducer/evidence retention bug, not a build failure.

## Root Cause

The successful work session fetched and extracted the source archive in an
earlier command, then proved source/build identity in a final command. The
earlier source command later failed during configure/build, and the archive
hash line was clipped out of the retained command evidence. The final command
read back the saved upstream page/tag metadata, archive hash, archive root, and
runtime proof, but `long_build_substrate` only accepted explicit
`authority_page_saved` / `archive_root` markers for saved-page source proof.

The result was overly narrow recognition:

`saved authority files + sha256sum archive + tar root + final artifact proof`

was treated as no source authority signal.

## Repair

Add a provider-neutral saved-source readback signal:

- command must run with `errexit` still enabled
- command must read back an authority page or tag metadata
- command must run a real archive hash command over an archive path
- command must run a real archive listing command over an archive path
- the hash and archive listing must refer to the same archive path
- the hash/list commands must be top-level required commands, not guarded by
  `if`, `while`, `do`, `|| true`, `&&` control-flow, pipes, redirection,
  redirected compound commands, `exec` stdout redirection, or backgrounding
- output must include source-authority metadata, an archive hash line, and an
  archive root listing

This keeps echoed marker-only proofs rejected while allowing a later final
proof command to close source authority when long source-acquisition output was
clipped.

After review, guarded `if [ -f archive ]; then sha256sum archive; ...; fi`
readback remains intentionally rejected. Shell xtrace is not a trustworthy
enough discriminator because a later command can print fake xtrace-like lines to
stderr. The same conservative rule rejects hidden or non-required readbacks:
direct redirection, pipeline redirection, `exec`-redirected stdout,
brace/subshell compound redirection including `time`, and backgrounded
readbacks. The work-loop source acquisition guidance now steers models to use
top-level failing readback commands such as `test -f archive; sha256sum archive;
tar -tzf archive` for the live rerun.

## Validation

Focused source-authority tests:

`uv run pytest --no-testmon -q tests/test_long_build_substrate.py -k 'saved_authority_page or source_authority'`

Result: `154 passed, 74 deselected`.

Combined regression:

`uv run pytest --no-testmon -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py`

Result: `1223 passed, 1 warning, 67 subtests passed`.

Ruff:

`uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py`

Result: passed.

Diff check and ledger parse:

- `git diff --check`: passed
- `jq -c . proof-artifacts/m6_24_gap_ledger.jsonl`: passed

Review:

- `codex-ultra` session `019de6a8-c827-75f3-974b-67a08d05b5b2`: `STATUS: APPROVE`

Replay against the live passing run:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-post-loop-source-signal-compile-compcert-1attempt-20260502-1145/.../mew-report.json`

Result after the conservative hardening:

- `source_authority`: `unknown`
- `target_built`: `satisfied`
- `default_smoke`: `satisfied`
- state: `ready_for_final_proof`
- `current_failure`: `null`
- blockers: `[]`

That historical run used guarded `if` readback, so it stays a negative fixture.
The next live rerun must produce unguarded top-level archive readback evidence.

## Next Action

Run one same-shape `compile-compcert` speed_1 after review. Do not run proof_5
or broad measurement until the live rerun records all closeout fields:

- Harbor reward `1.0`
- runner errors `0`
- command transcript exit `0`
- `mew-report.work_exit_code=0`
- `source_authority=satisfied`
- `current_failure=null`
- `strategy_blockers=[]`
