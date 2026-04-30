# M6.24 Long Dependency Build State Repair - 2026-04-30

Gap:

`long_dependency_build_state_progress_contract_missing`

Trigger evidence:

- `docs/M6_24_COMPILE_COMPCERT_SPEED_RERUN_2026-04-30.md`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-long-toolchain-compile-compcert-1attempt-20260430-0317/result.json`

## Problem

For long dependency/toolchain/source builds, mew could make real prerequisite
progress but fail to preserve enough build-state semantics across turns.

The `compile-compcert` rerun reached a compatible opam/Coq path, generated
CompCert dependencies, and started `make ccomp`, but the final artifact
`/tmp/CompCert/ccomp` was still missing when the external verifier ran. The
missing contract was not "more permissions"; it was explicit continuity between
prerequisite progress, final build continuation, and final artifact proof.

## Repair

This repair adds a generic implementation-lane contract:

- classify long dependency/toolchain/source-build tasks;
- extract required final absolute artifacts from task text;
- block finish when only prerequisite/configure/dependency/partial-build
  evidence exists and the required final artifact is unproven;
- surface `work_session.resume.long_dependency_build_state` with:
  - progress stages such as package setup, toolchain selection, configure,
    dependency generation, and build attempt;
  - expected and missing final artifacts;
  - latest build command and incomplete reason;
  - a continuation-oriented suggested next action;
- update THINK guidance to avoid restarting package/source setup after a
  compatible toolchain path is found.

## Validation

Focused validation:

```text
uv run pytest tests/test_acceptance.py -k 'long_dependency' --no-testmon -q
uv run pytest tests/test_work_session.py -k 'long_dependency_build_state or work_think_prompt_guides_independent_reads_to_batch' --no-testmon -q
uv run ruff check src/mew/acceptance.py src/mew/work_session.py src/mew/work_loop.py tests/test_acceptance.py tests/test_work_session.py
```

Result:

- acceptance long-dependency tests: `4 passed`
- work-session long-dependency tests: `2 passed`
- work-session/prompt tests: `2 passed`
- ruff: passed

## Review Follow-up

`codex-ultra` reviewed commit `ef5abf8` and found two correctness risks before
the validation rerun:

- command-only executable smoke proofs such as
  `test -x /tmp/CompCert/ccomp && /tmp/CompCert/ccomp -version` could be
  rejected when stdout did not repeat the artifact path;
- a fresh long-dependency session with no completed progress could still emit a
  "resume existing source tree/toolchain" hint because missing artifacts were
  initialized before any progress existed.

The follow-up fix keeps the final-artifact blocker strict, but evaluates the
successful tool command together with stdout/stderr, and suppresses
`long_dependency_build_state` until there is actual build progress or proven
artifact state.

The same `codex-ultra` review session re-reviewed the follow-up diff and
returned `APPROVED`.

## Next Validation

Run a one-trial same-shape speed rerun for `compile-compcert`.

Do not resume broad measurement and do not escalate to five trials before this
speed rerun is recorded.

## Follow-up Speed Rerun

The follow-up speed rerun is recorded in:

- `docs/M6_24_COMPILE_COMPCERT_FOLLOWUP_RERUN_2026-04-30.md`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-long-build-state-followup-compile-compcert-1attempt-20260430-0418/result.json`

Result:

- reward: `0/1`
- runner errors: `0`
- runtime: `31m 43s`
- behavior: partial report before oneshot completion, `29/30` steps used,
  one build command still running at handoff

The repair moved behavior in the right direction: mew preserved build state,
used the compatible opam Coq `8.16.1` path, ran `make depend`, and entered the
real `make -j2 ccomp` proof build. It did not close the gap because it still
spent too much wall budget on invalidated package/toolchain paths, discovered
dependency-generation order late, and did not surface the actively running
final build command as the latest long-build state.

## v0.1 Repair

The next bounded generic repair is:

`long_dependency_toolchain_compatibility_and_continuation_contract`

It extends v0 without adding a new lane:

- reentry state now surfaces strategy blockers such as toolchain version
  mismatch, package source/name mismatch, preinstalled-tool conflict, and
  dependency-generation order issues;
- running or interrupted build commands are included as active long-build state
  so partial reports can preserve the latest continuation command;
- THINK guidance now tells long source-build tasks to probe explicit version
  constraints before distro package installs, avoid retrying invalidated
  package/toolchain paths, run dependency-generation/configure targets before
  target-specific builds when errors indicate missing generated dependencies,
  and set a bounded per-command timeout for genuinely long build commands.

Focused validation:

```text
uv run pytest tests/test_acceptance.py --no-testmon -q
uv run pytest tests/test_work_session.py -k 'long_dependency or work_think_prompt_guides_independent_reads_to_batch or preserves_bounded_run_command_timeout or system_service' --no-testmon -q
uv run ruff check src/mew/work_session.py src/mew/work_loop.py tests/test_work_session.py
jq empty proof-artifacts/m6_24_gap_ledger.jsonl
git diff --check
```

Result:

- acceptance tests: `94 passed`
- focused work-session tests: `5 passed`
- ruff: passed
- gap ledger JSON: valid
- diff whitespace: clean
- codex-ultra review session `019ddad3-4dd2-7ac1-9285-4cc44c5f7b28`: `APPROVED`

Next validation remains a one-trial same-shape speed rerun for
`compile-compcert`.

## v0.3 Repair

`long_dependency_toolchain_compatibility_override_order_contract`

Resource-normalized `compile-compcert` proof reached `1/2` valid completed
trials before the `5/5` close target became impossible. The failed completed
trial grounded the source tree and entered real build work, but after distro
Coq version rejection it spent budget on an alternate OPAM toolchain instead of
first trying cheap source-provided compatibility/override configure paths.

Changes:

- long-dependency resume state now surfaces
  `compatibility_override_probe_missing` when a source-build configure step
  rejects a dependency version and no cheap compatibility/help probe is visible;
- THINK guidance now tells source-build tasks to inspect `./configure --help`
  or equivalent project help and try source-provided compatibility/override
  flags before constructing an alternate toolchain from scratch;
- alternate toolchain construction remains allowed after the cheap override path
  is invalidated.

Focused validation:

```text
uv run pytest tests/test_work_session.py -k 'long_dependency or work_think_prompt_guides_independent_reads_to_batch' --no-testmon -q
uv run ruff check src/mew/work_session.py src/mew/work_loop.py tests/test_work_session.py
jq empty proof-artifacts/m6_24_gap_ledger.jsonl
git diff --check
```

Result:

- focused work-session tests: `3 passed`
- ruff: passed
- gap ledger JSON: valid
- diff whitespace: clean

Next validation remains a one-trial same-shape speed rerun for
`compile-compcert`.

## v0.3 Speed Rerun

The v0.3 same-shape speed rerun passed:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compat-override-compile-compcert-1attempt-20260430-0843/2026-04-30__08-43-13/result.json
```

Result:

- reward: `1.0`
- runner errors: `0`
- runtime: `28m 4s`
- external verifier: `3 passed`

The run inspected configure help and the Coq version rejection, tried
`./configure -ignore-coq-version`, then moved to a compatible OPAM Coq `8.16.1`
path, built `/tmp/CompCert/ccomp`, installed runtime libraries, and passed the
external verifier.

Next validation is resource-normalized proof_5 for the same shape:
`compile-compcert -k 5 -n 1`.

## v0.4 Repair

`long_dependency_runtime_link_library_contract`

Resource-normalized `compile-compcert` proof after v0.3 reached `2/3` valid
completed trials before the `5/5` close target became impossible. The failed
completed trial built `/tmp/CompCert/ccomp` and completed a local smoke, but the
external verifier failed because the compiler could not link against its runtime
library:

```text
/usr/bin/ld: cannot find -lcompcert: No such file or directory
ccomp: error: linker command failed with exit code 1
```

Changes:

- long-dependency resume state now surfaces `runtime_link_library_missing` for
  source-build/toolchain link failures such as `cannot find -l...`;
- long-dependency next guidance now says missing runtime/link-library failures
  require installing or configuring the project runtime/library target before
  finish;
- THINK guidance now says a trivial return-only smoke is not enough for
  compiler/toolchain tasks with runtime or standard-library link requirements.

Focused validation:

```text
uv run pytest tests/test_work_session.py -k 'long_dependency or work_think_prompt_guides_independent_reads_to_batch' --no-testmon -q
uv run ruff check src/mew/work_session.py src/mew/work_loop.py tests/test_work_session.py
```

Result:

- focused work-session tests: `4 passed`
- ruff: passed

Next validation remains a one-trial same-shape speed rerun for
`compile-compcert`.

## v0.2 Speed Rerun

The v0.2 same-shape speed rerun passed:

- result:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-wall-target-compile-compcert-1attempt-20260430-0615/2026-04-30__06-14-47/result.json`
- trial:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-wall-target-compile-compcert-1attempt-20260430-0615/2026-04-30__06-14-47/compile-compcert__42Z5Wsw/result.json`
- reward: `1.0`
- errors: `0`
- runtime: `25m 38s`

Observed behavior:

- the v0.2 strategy blocker surfaced the early untargeted `make -j2 all`;
- mew recovered from Menhir/toolchain and dependency-generation blockers;
- the final material build used `make -j2 ccomp`;
- the external verifier passed executable, functional smoke, and unsupported
  feature checks.

Residual calibration signal:

- the final report still carried stale `long_dependency_build_state` missing
  artifact entries after verifier success. This is report/resume cleanup
  evidence, not a blocker for the selected score repair.

Next validation is a five-trial same-shape proof for `compile-compcert`.

## v0.1 Speed Rerun Diagnostic

The v0.1 speed rerun is recorded in:

- `docs/M6_24_COMPILE_COMPCERT_V01_RERUN_2026-04-30.md`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-long-dep-v01-compile-compcert-1attempt-20260430-0509/result.json`

This run is diagnostic, not score evidence:

- Harbor ended with `CancelledError` because the operator stopped the runaway
  trial after the intended wall-clock window was exceeded;
- mew partial report was still `phase=running`;
- the active `run_command` had been running inside the final build for `1693s`;
- `/tmp/CompCert/ccomp` was still missing/unproven.

The repair improved state visibility, but exposed two generic loop gaps:

- running `run_command` / `run_tests` calls were not capped to the remaining
  `mew work --max-wall-seconds` budget;
- the selected build command was `make -j"$(nproc)"`, a full project/proof
  build, while the task required one named final artifact:
  `/tmp/CompCert/ccomp`.

## v0.2 Repair

The next bounded generic repair keeps the same lane/profile:

`long_dependency_wall_clock_and_targeted_artifact_build_contract`

Changes:

- `run_command` / `run_tests` tool parameters are capped to the remaining
  `mew work` wall-clock budget before tool execution;
- work-session command execution uses process-group termination for bounded
  command timeouts, so long build children cannot survive after the parent
  command is timed out;
- if the remaining budget cannot fit a bounded tool call, mew records a
  `wall_timeout` step instead of starting the tool;
- capped tool calls record `wall_timeout_ceiling` in their parameters;
- long-dependency resume state surfaces
  `untargeted_full_project_build_for_specific_artifact` when a bare `make` or
  option-only `make -j...` is used even though the task names a specific final
  artifact. This includes chained/wrapped invocations such as
  `cd ... && make -j...`, `timeout 120 make -j...`, and variable-assignment
  forms such as `make -j2 CCOMP=/tmp/CompCert/ccomp`;
- THINK guidance now tells source-build tasks to prefer the shortest explicit
  target that produces the required final artifact over full project, proof,
  doc, test, or all-target builds unless the task explicitly requires them.

Focused validation:

```text
uv run pytest tests/test_acceptance.py --no-testmon -q
uv run pytest tests/test_toolbox.py tests/test_work_session.py -k 'process_group or work_runner or untargeted_full_make or long_dependency or wall_budget or work_think_prompt_guides_independent_reads_to_batch or preserves_bounded_run_command_timeout or system_service' --no-testmon -q
uv run ruff check src/mew/toolbox.py src/mew/commands.py src/mew/work_session.py src/mew/work_loop.py tests/test_toolbox.py tests/test_work_session.py
jq empty proof-artifacts/m6_24_gap_ledger.jsonl
git diff --check
```

Result:

- acceptance tests: `94 passed`
- focused toolbox/work-session tests: `15 passed`, `5 subtests passed`
- ruff: passed
- gap ledger JSON: valid
- diff whitespace: clean
- codex-ultra review session `019ddb03-0e3b-7351-b1a3-c76549be27e3`: `APPROVED`

Next validation remains a one-trial same-shape speed rerun for
`compile-compcert`.
