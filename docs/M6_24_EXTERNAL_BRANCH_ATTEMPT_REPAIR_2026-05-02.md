# M6.24 External-Branch Attempt Repair - 2026-05-02

## Trigger

Same-shape `compile-compcert` speed rerun after the source-tail closeout
repair:

- Job: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-tail-closeout-recheck-compile-compcert-1attempt-20260502-1458-aptpy/result.json`
- Harbor trials: `1`
- Runner errors: `0`
- Harbor mean reward: `0.0`
- Runtime: about `30m22s`
- Trial: `compile-compcert__ds4YEh7`
- `mew-report.work_exit_code`: `1`

The external verifier failed because `/tmp/CompCert/ccomp` did not exist.
Two earlier rerun attempts are invalid proof-infrastructure evidence, not
score evidence:

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-tail-closeout-recheck-compile-compcert-1attempt-20260502-1500/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-tail-closeout-recheck-compile-compcert-1attempt-20260502-1500-py3/result.json`

Both failed during harness setup because the container lacked the expected
Python binary before the agent could run.

## Root Cause

The live run reached the known CompCert dependency branch surface but did not
try the source-provided external/prebuilt branch before starting a
version-pinned OPAM source-toolchain path.

Observed path:

1. Prebuilt distro dependencies were available through `apt`.
2. Configure/help exposed external branch flags such as
   `-use-external-Flocq` and `-use-external-MenhirLib`.
3. A plain `-ignore-coq-version` configure path failed with dependency/API
   mismatch such as Menhir API-library location errors.
4. mew then started `opam install ... coq.8.16.1 ...` source-toolchain work.
5. The OPAM path failed with `Error: Unbound module MenhirLib.General` and
   exhausted the wall/model budget before `/tmp/CompCert/ccomp` existed.

This is not another source-tail closeout reducer bug. It is a strategy-ordering
miss in the long-dependency implementation profile.

## Repair

- Add a `source_toolchain_before_external_branch_attempt` strategy blocker
  when all of the following hold:
  - required artifact is still missing,
  - prebuilt package-manager dependency evidence exists,
  - project output exposes an external/prebuilt/system compatibility branch,
  - a dependency/API mismatch has been observed,
  - no actual external/prebuilt/system configure attempt is visible,
  - version-pinned source-toolchain work begins.
- Detect mismatch independently of whether the external-branch help appeared
  before or after the failed configure output.
- Avoid a false positive where successful help text merely describes an
  `API library`; API-library text counts as mismatch only in failed/error call
  context.
- Map the new blocker through the long-build reducer as
  `dependency_strategy_unresolved` with a specific clear condition:
  attempt the exposed external/prebuilt/system dependency branch before
  version-pinned source-toolchain work.
- Update the long-dependency THINK guidance so a plain ignore-version retry is
  not treated as equivalent to trying the exposed external/prebuilt branch.

## Validation

- Focused work-session subset:
  - `uv run pytest -q tests/test_work_session.py -k 'source_toolchain_before_external_branch_attempt or source_toolchain_after_external_branch_attempt or source_toolchain_after_override_attempt or external_branch_help_probe or successful_help_api_library' --no-testmon`
  - `7 passed, 860 deselected`
- Combined long-build/work-session/acceptance subset:
  - `uv run pytest -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py -k 'long_build or long_dependency or source_toolchain or external_branch or source_authority or default_smoke' --no-testmon`
  - `284 passed, 949 deselected, 22 subtests`
- Full long-build/work-session:
  - `uv run pytest -q tests/test_work_session.py tests/test_long_build_substrate.py --no-testmon`
  - `1101 passed, 1 warning, 67 subtests`
- Ruff:
  - `uv run ruff check src/mew/work_session.py src/mew/work_loop.py src/mew/long_build_substrate.py tests/test_work_session.py`
  - passed
- Diff check:
  - `git diff --check`
  - passed

Local replay of the live `20260502-1458-aptpy` report after repair marks the
same failure family as:

- `failure_class=dependency_strategy_unresolved`
- `legacy_code=source_toolchain_before_external_branch_attempt`
- blocker layer: `profile_contract`

## Review

`codex-ultra` session `019de766-9116-7671-b95c-dfa85da2b005` first returned
`REQUEST_CHANGES` for:

- mismatch-before-help ordering,
- successful help output mentioning `API library` as a false-positive risk.

Both were fixed with regressions. The same session then returned
`STATUS: APPROVE`.

Review record:

- `docs/REVIEW_2026-05-02_M6_24_EXTERNAL_BRANCH_ATTEMPT_CODEX.md`

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
