# M6.24 Long-Command Continuation Speed Rerun - 2026-05-02

## Trigger

Same-shape `compile-compcert` speed rerun after long-command continuation
Phase 6 transfer closeout:

- Job:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-long-command-continuation-compile-compcert-1attempt-20260502-2040`
- Trial: `compile-compcert__LCwdHHw`
- Harbor trials: `1`
- Runner errors: `0`
- Harbor mean reward: `0.0`
- Runtime: about `30m28s`
- `mew-report.work_exit_code`: `1`
- `work_report.stop_reason`: `wall_timeout`

The external verifier failed because `/tmp/CompCert/ccomp` did not exist.

## What The Run Actually Tested

This did **not** exercise the long-command continuation substrate:

- `timeout_shape.latest_long_command_run_id=null`
- `timeout_shape.latest_long_command_status=null`
- `resume.long_build_state.long_command_runs=[]`

The run regressed before the final continuation point. It started OPAM
source-toolchain installation for `coq.8.16.1` after discovering a
source-script compatibility hook, then timed out during `opam install`.

## Observed Path

1. The run fetched and extracted the `v3.13.1` source archive.
2. Plain `./configure x86_64-linux` failed on unsupported Coq 8.18 and missing
   Menhir API library.
3. A compatibility-hook inspection of `configure` showed:
   `LIBRARY_MENHIRLIB=local  # external`.
4. It installed `libmenhir-ocaml-dev` and a plain
   `./configure -ignore-coq-version x86_64-linux` succeeded.
5. `make depend` succeeded, but `make ccomp` failed under unsupported Coq 8.18.
6. Instead of trying the exposed external/system dependency branch, the model
   started a version-pinned OPAM Coq 8.16.1 toolchain path.
7. The OPAM command consumed the remaining wall budget and timed out before
   `/tmp/CompCert/ccomp` existed.

## Classification

Primary class:
`dependency_strategy_unresolved`.

Specific blocker:
`source_toolchain_before_external_branch_attempt`.

This is not a new continuation failure. The generic continuation work remains
valid, but the next same-shape proof cannot spend another run until the
strategy-regression evidence is repaired.

## Repair

The repair keeps the change generic:

- Treat configure/source-script compatibility-hook variables such as
  `LIBRARY_* = local # external` as external/prebuilt/system branch evidence,
  but only when the hook appears in observed command output, not only in the
  query command text or shell xtrace.
- Recognize assignment-style branch attempts such as
  `LIBRARY_*=external ./configure ...` as attempts that clear the
  source-toolchain-before-external-branch blocker.
- Preserve the existing rule that a plain ignore-version/allow-unsupported
  configure retry is not equivalent to trying the exposed external/prebuilt
  branch.
- Ensure replay of this report selects
  `source_toolchain_before_external_branch_attempt` as the current failure,
  not only the earlier narrow-help probe blocker.

## Validation

- Focused work-session subset:
  - `uv run pytest -q tests/test_work_session.py -k 'config_script_external_hook or query_only_external_hook_text or assignment_style_external_attempt or source_toolchain_before_external_branch_attempt or external_branch_help_probe or successful_help_api_library or source_toolchain_after_external_branch_attempt or source_toolchain_after_override_attempt' --no-testmon`
  - `10 passed, 867 deselected`
- Broader long-build/work-session/acceptance subset:
  - `uv run pytest -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py -k 'long_build or long_dependency or source_toolchain or external_branch or source_authority or default_smoke' --no-testmon`
  - `309 passed, 956 deselected, 22 subtests`
- Ruff:
  - `uv run ruff check src/mew/work_session.py src/mew/work_loop.py tests/test_work_session.py`
  - passed
- Gap ledger JSONL parse and diff check:
  - passed
- Local replay of this report after repair selects:
  - `current_failure.legacy_code=source_toolchain_before_external_branch_attempt`
  - `current_failure.clear_condition=the exposed external/prebuilt/system dependency branch is attempted before version-pinned source toolchain work`

## Next

Run broader targeted validation and codex-ultra review if needed, then rerun one
same-shape `compile-compcert` speed_1. Do not run `proof_5` or broad
measurement before that rerun records a clean pass or a newer narrower gap.
