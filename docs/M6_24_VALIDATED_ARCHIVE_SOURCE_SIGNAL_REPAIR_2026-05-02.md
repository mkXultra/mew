# M6.24 Validated Archive Source Signal Repair - 2026-05-02

## Context

After commit `7a26d8f`, the same-shape `compile-compcert` speed rerun passed
the external Terminal-Bench verifier:

- Harbor job: `mew-m6-24-authority-page-source-signal-compile-compcert-1attempt-20260502-0828`
- Trial: `compile-compcert__ZmDm6bA`
- Harbor reward: `1.0`
- runner errors: `0`
- command transcript exit: `0`
- `mew-report.work_exit_code`: `0`

The internal close gate still failed:

- `source_authority`: `unknown`
- `current_failure`: stale `target_selection_overbroad`
- `strategy_blockers`: stale historical blockers

The task was actually solved. The defect was in evidence reduction.

## Diagnosis

The source acquisition step used a generic non-Python archive-discovery loop:

- fetch upstream/download pages
- try candidate release/tag archive URLs
- `curl -fL --retry ... "$url"`
- `tar -tzf` to validate the downloaded archive
- `tar -xzf` and move the extracted root to `/tmp/CompCert`

That is a valid source-authority pattern, but the previous classifier depended
on an authority line surviving `CommandEvidence` head/tail clipping, such as
`authority_page_saved=...` or `authority_archive_url=...`.

In this live run, the relevant provenance line was in the middle of a large
command output and was clipped away. The command text itself still contained the
trusted acquisition structure, so source authority should be recoverable from
the command contract plus terminal success.

## Repair

`src/mew/long_build_substrate.py` now recognizes a validated archive source
acquisition when all are true:

- command starts under `set -e` / `set -eu` and does not disable `errexit`
- source fetch is non-Python and failure is not masked
- literal command URLs include an authoritative release/archive URL
- the command validates the archive (`tar -t...` or `unzip -t...`)
- the command extracts the archive and moves the extracted root into a source
  directory
- output head/tail do not contain a build-failure signal

The signal is intentionally generic. It is not tied to CompCert or
Terminal-Bench.

## Guardrails

Added tests cover:

- accepting a `for url in ...; curl "$url"; tar -tzf; tar -xzf; mv "$root"` loop
  even when output is too large for the authority line to survive clipping
- rejecting archive-loop downloads that do not validate and extract the archive
- rejecting comment-only authoritative URLs when the fetched archive is from an
  unrelated mirror
- rejecting loops where the fetched archive is ignored and a different local
  archive is validated/extracted
- rejecting no-download URL probes such as `curl -I "$url"`
- rejecting validation, extraction, or root-move commands that appear only in
  `echo`, comments, or heredoc text
- rejecting loop selected-URL sentinels that appear only in comments, `echo`,
  or heredoc text
- rejecting candidate loops without stale archive removal before the fetch
- rejecting entire candidate loops that appear only in an unexecuted heredoc
- rejecting direct authoritative archive fetches that appear only in an
  unexecuted heredoc
- rejecting direct and candidate-loop archive fetches inside unexecuted shell
  function bodies
- rejecting candidate loops nested under unexecuted outer conditionals
- rejecting direct authoritative archive fetches nested under unexecuted outer
  conditionals
- accepting standard same-line `for url in ...; do` archive loops
- rejecting direct and candidate-loop fetches nested under unexecuted outer
  `while` / `until` bodies, including split-line `while ...` / `do` forms
- rejecting direct authoritative archive fetches inside split-line
  `if ...` / `then` branches
- rejecting direct and candidate-loop fetches inside control blocks that start
  after another command on the same physical line, such as `:; if false; then`

Existing negative tests still cover spoofed printed URLs, local identity only,
masked fetches, non-download curl probes, partial range downloads, HEAD-only
probes, Python remote source acquisition, and authority-page claims without
archive identity.

## Validation

- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py -k 'source_authority'`: `111 passed`
- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py`: `185 passed`
- `uv run pytest --no-testmon -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py`: `1180 passed`, `1 warning`, `67 subtests`
- `uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py`: passed
- `git diff --check`: passed

## Next Gate

Run one more live same-shape `compile-compcert` speed rerun after this repair.

Required closeout before proof_5:

- Harbor reward `1.0`
- runner errors `0`
- command transcript exit `0`
- `mew-report.work_exit_code=0`
- `source_authority=satisfied`
- `current_failure=null`
- `strategy_blockers=[]`

Do not run proof_5 or broad measurement before this live gate is recorded.
