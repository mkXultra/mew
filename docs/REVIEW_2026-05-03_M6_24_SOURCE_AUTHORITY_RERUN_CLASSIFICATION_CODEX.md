# Review 2026-05-03 - M6.24 Source-Authority Rerun Classification

STATUS: RECOMMEND_REPAIR

## Summary

The latest same-shape `compile-compcert` speed_1 moved the prior
source-authority path-correlation blocker: the internal long-build state now
records `source_authority=satisfied`. It did not close the repair chain. Harbor
scored `0.0` with runner errors `0`; `/tmp/CompCert/ccomp` existed and was
executable, but the functional verifier failed with `/usr/bin/ld: cannot find
-lcompcert`.

Primary current gap class: `long_command_continuation_dispatch_not_engaged`.

Immediate task symptom: `runtime_link_failed` / default runtime library missing.

Secondary reducer defect: the internal state selected stale dependency/target
state (`dependency_generation=blocked`, `target_selection_overbroad`) instead
of the later runtime-link failure.

## Evidence

- Top-level result:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-authority-path-correlation-compile-compcert-1attempt-20260502-2336/result.json`
  records one trial, `n_errors=0`, mean reward `0.0`.
- Trial result:
  `compile-compcert__Awb78Qn/result.json` records matched timeout shape
  (`agent_timeout_seconds=1800`, `mew_max_wall_seconds=1740`) and
  `latest_long_command_run_id=null`.
- Verifier:
  `verifier/test-stdout.txt` passed the executable and unsupported-feature
  checks, then failed `test_compcert_valid_and_functional` because default
  linking could not find `-lcompcert`.
- Mew report:
  `mew-report.json` has `work_exit_code=1`, `work_report.stop_reason=wall_timeout`,
  and `timeout_shape.latest_long_command_run_id=null`.
- Long-build state:
  `source_authority=satisfied`, `configure=satisfied`,
  `dependency_generation=blocked`, `target_built=blocked`,
  `default_smoke=unknown`, `long_command_runs=[]`.

## Findings

1. Source authority closed for this rerun.

   The repair moved the previous source-authority blocker: the reduced
   long-build state marks the `source_authority` stage `satisfied`. The run then
   reached external Flocq, `make depend`, and a `make -j2 ccomp` continuation
   far enough for the external verifier to find `/tmp/CompCert/ccomp`.

2. The external failure is runtime-link, not source-authority or dependency
   generation.

   The verifier failed only when compiling/linking a positive C probe through
   `/tmp/CompCert/ccomp`, with `cannot find -lcompcert`. That is default runtime
   library lookup/install evidence. The report's `dependency_generation=blocked`
   and `target_selection_overbroad` current failure are stale relative to the
   later successful source/config/dependency/build progress.

3. Production long-command continuation is not actually dispatched.

   `src/mew/toolbox.py:627` defines `ManagedCommandRunner`, but `rg` finds no
   production import or use of it outside tests. `src/mew/work_session.py:2208`
   still routes work commands through `run_command_record_streaming` or
   `run_command_record`; `src/mew/work_session.py:2539` and `:2576` call that
   blocking path for `run_tests` and `run_command`.

   `src/mew/commands.py:7569` computes a long-command budget policy and
   `src/mew/commands.py:6391` attaches `long_command_budget` metadata to tool
   parameters, but `src/mew/commands.py:7801` still calls the normal
   `execute_work_tool_with_output` path. `src/mew/long_build_substrate.py:667`
   can reduce supplied `long_command_runs`, but this run had none and no source
   path populates them.

4. The next repair should be generic dispatch, not a compile-compcert solver.

   The smallest repair matching
   `docs/DESIGN_2026-05-02_M6_24_LONG_COMMAND_CONTINUATION.md` is to wire the
   existing managed runner into `run_command`/`run_tests` when the feature gate
   and `long_command_budget` mark a planned long-build stage. Start should
   create a persisted `LongCommandRun(status=running|yielded)` plus nonterminal
   `CommandEvidence`; poll/finalize should create separate terminal evidence;
   only terminal success may satisfy artifact/default-smoke proof. This keeps
   the fix at the tool/runtime layer and avoids adding a CompCert-specific
   runtime install recipe.

5. A small reducer regression should travel with the dispatch repair.

   The runtime-link symptom must be preserved as evidence: when a later command
   invokes the required artifact and default linking fails with missing
   libraries, stale dependency-generation and overbroad-target blockers must not
   be selected as the current failure. This should be a generic fixture, not a
   `libcompcert.a` special case.

## Required Tests

- Work-loop dispatch: a synthetic long-build `run_command` with long-command
  budget starts through `ManagedCommandRunner`, persists exactly one active
  `LongCommandRun`, records nonterminal command evidence, and reports
  `latest_long_command_run_id`.
- Poll/finalize success: a yielded command later exits `0`, writes separate
  terminal `CommandEvidence`, links it from `LongCommandRun`, and only that
  terminal evidence can satisfy artifact proof.
- Poll/finalize failure and timeout: nonzero, timed-out, killed, interrupted,
  and orphaned managed commands remain non-success evidence and derive
  `poll_long_command` or `resume_idempotent_long_command` recovery decisions
  without reopening stale source/dependency blockers.
- Budget policy: start/resume require `yield_after < effective_timeout` and
  proof reserve; poll can use a smaller wait; repeated same-timeout resume is
  blocked unless explicitly diagnostic.
- Ownership: poll/finalize rejects missing owner token, pid/process-group
  mismatch, cwd mismatch, command-hash mismatch, and a second active managed
  command.
- Output owner: bounded head/tail/output-ref behavior is deterministic and
  retained for active and terminal runs.
- Reducer regression: a non-CompCert fixture where source/config/dependency
  build progress is satisfied, the required artifact is invokable, and a
  default smoke fails with missing `-l...` selects `runtime_link_failed` (or the
  existing generic runtime-link class) instead of dependency-generation stale
  state.
- Harbor/reporting: a synthetic same-shape report includes non-null
  `timeout_shape.latest_long_command_run_id` when a managed run is active or
  finalized, and verifier-ready success is refused while any run is nonterminal.
