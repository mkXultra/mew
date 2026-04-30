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

## v0.7 Runtime Install Target Repair

The v0.6 speed rerun is recorded in:

- `docs/M6_24_DEFAULT_RUNTIME_LINK_PATH_COMPILE_COMPCERT_SPEED_RERUN_2026-04-30.md`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-default-runtime-link-path-compile-compcert-1attempt-20260430-1508/2026-04-30__15-07-47/result.json`

The failure shape improved but did not score:

- mew built `/tmp/CompCert/ccomp`;
- mew did not accept a custom `-stdlib` smoke proof as completion;
- mew attempted default runtime install;
- `make -C runtime install` failed because `libcompcert.a` had not been built;
- the session then exhausted wall/model budget before default-link proof.

The bounded generic repair is:

`long_dependency_runtime_install_requires_runtime_target_contract`

Changes:

- work-session resume now surfaces
  `runtime_install_before_runtime_library_build` when an install error line
  itself names a missing runtime library artifact such as `libcompcert.a`;
- the blocker is cleared if a later successful command builds or installs that
  runtime library, or if a later default compile/link smoke proof passes;
- after a later successful runtime-library build/install clears one blocker,
  scanning continues so a second later missing-library install failure remains
  visible;
- quiet successful exact runtime install retries clear the blocker even when
  their output omits copied library names. This is parsed through make targets
  and `cwd`/`-C runtime`, so unrelated targets such as `uninstall` do not clear
  the blocker;
- long-dependency suggested-next text now tells the model to build the shortest
  explicit runtime-library target first, then retry install and default-link
  smoke;
- THINK guidance includes the same rule for compiler/toolchain source-build
  tasks.

Focused validation:

```text
uv run pytest tests/test_work_session.py -k 'runtime_install_before_runtime_library or default_runtime_link or custom_runtime_path or missing_runtime_link_library or work_think_prompt_guides_independent_reads_to_batch' --no-testmon -q
uv run pytest tests/test_work_session.py -k 'long_dependency or runtime_install_before_runtime_library or runtime_link_library or default_runtime' --no-testmon -q
uv run ruff check src/mew/work_session.py src/mew/work_loop.py tests/test_work_session.py
```

Result:

- focused runtime-install/default-link tests: `11 passed`
- broader long-dependency focused tests: `5 passed`
- ruff: passed
- codex-ultra review session `019ddd2b-8895-7771-b617-ef75359c2e7a`:
  `APPROVED` after two review/fix rounds

Next validation is a one-trial same-shape speed rerun for `compile-compcert`.
Broad measurement and proof_5 remain paused.

## v1.0 Final Recovery-Budget Reserve

The OAuth-refresh proof rerun is recorded in:

- `docs/M6_24_OAUTH_REFRESH_COMPILE_COMPCERT_PROOF_5_2026-04-30.md`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-oauth-refresh-compile-compcert-5attempts-seq-20260430-2256/result.json`

The proof infrastructure repair worked: no `HTTP 401 token_expired` recurrence
was observed with refreshable `~/.codex/auth.json`. The close gate still missed:

- valid completed trials reached `1/2`;
- the failed valid trial built `/tmp/CompCert/ccomp`;
- default functional smoke failed with `/usr/bin/ld: cannot find -lcompcert`;
- the session then had only `14.873s` wall time left, leaving no useful model
  recovery turn to run the already-known runtime-library build/install path.

The bounded generic repair is:

`long_dependency_final_recovery_budget_after_failed_validation`

Changes:

- `mew work` now detects long dependency/toolchain build commands with long
  timeouts and final validation smoke markers;
- those commands reserve `60s` of wall budget before execution rather than only
  the normal `2s` tool reserve;
- if a recent runtime-link/runtime-install blocker is already visible, the
  follow-up recovery command can spend that reserved budget instead of being
  re-reserved and blocked;
- ordinary short tool calls keep the old timeout behavior.

Focused validation:

```text
UV_CACHE_DIR=/tmp/uv-cache uv run pytest --no-testmon tests/test_work_session.py -k 'wall_budget or wall_timeout or long_build_validation_command' -q
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src/mew/commands.py tests/test_work_session.py
```

Result:

- focused wall-budget tests: `8 passed`
- ruff: passed
- broader regression (`tests/test_work_session.py`, `tests/test_codex_api.py`,
  `tests/test_model_backends.py`): `858 passed`, one multiprocessing warning
- `codex-ultra` review session `019ddeed-31bf-7373-a6f8-b417b0865203`:
  `APPROVE` after the recovery-command re-reservation regressions were added

The one-trial same-shape speed proof passed:

```text
docs/M6_24_RECOVERY_BUDGET_COMPILE_COMPCERT_SPEED_RERUN_2026-05-01.md
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-recovery-budget-compile-compcert-1attempt-20260501-0018/result.json
```

Result:

- reward: `1.0`
- runner errors: `0`
- runtime: `29m 25s`
- work-session stop reason: `finish`
- external verifier: `3 passed`

Next validation is resource-normalized proof_5 for `compile-compcert` with
sequential `-k 5 -n 1` and refreshable `~/.codex/auth.json`. Broad measurement
remains paused.

## v1.1 Malformed JSON Plan Recovery

The v1.0 resource-normalized proof is recorded in:

- `docs/M6_24_RECOVERY_BUDGET_COMPILE_COMPCERT_PROOF_5_2026-05-01.md`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-recovery-budget-compile-compcert-5attempts-seq-20260501-0055/result.json`

The proof reached `2/3` valid completed trials before the frozen `5/5` close
target became impossible. The failed valid trial did not exercise
long-dependency build behavior: the first model turn returned a malformed JSON
plan and `mew work` stopped with `stop_reason=model_error`.

The repair is:

`work_oneshot_malformed_json_plan_recovery_missing`

Changes:

- one-shot work treats backend `failed to parse JSON plan` as a recoverable
  transient model error;
- generic `model returned invalid JSON` remains non-recoverable;
- existing one-shot continue-after-model-error behavior handles the retry.

Focused validation:

```text
UV_CACHE_DIR=/tmp/uv-cache uv run pytest --no-testmon tests/test_work_session.py -k 'recoverable_work_model_error or continues_after_recoverable_model_error or does_not_continue_after_recoverable_model_error' -q
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src/mew/commands.py tests/test_work_session.py
```

Result:

- focused tests: `3 passed`
- ruff: passed
- broader work-session regression: `826 passed`, one multiprocessing warning,
  `67 subtests passed`
- `codex-ultra` review session `019ddf49-e29d-7140-bd17-24c9d889c0a8`:
  `APPROVE`

Next validation is a one-trial same-shape speed rerun for `compile-compcert`.
Broad measurement and proof_5 remain paused.

## v0.8 Source Archive Identity / Empty Response Recovery Repair

The v0.7 speed rerun is recorded in:

- `docs/M6_24_RUNTIME_INSTALL_TARGET_COMPILE_COMPCERT_SPEED_RERUN_2026-04-30.md`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-install-target-compile-compcert-1attempt-20260430-1559/2026-04-30__16-07-36/result.json`

The run scored `0/1` with runner errors `0`, but it did not reach the runtime
install target blocker. It failed earlier:

- setup fetched the versioned `v3.13.1` release archive, then aborted because
  internal source markers did not repeat the exact patch suffix;
- `/tmp/CompCert/ccomp` remained missing;
- the next one-shot model turn failed with `response did not contain assistant
  text`, preventing recovery.

The bounded generic repair is:

`long_dependency_source_archive_identity_and_empty_response_recovery_contract`

Changes:

- work-session resume now surfaces
  `source_archive_version_grounding_too_strict` when a long dependency source
  build aborts because internal source markers omit an already archive/tag
  grounded patch-level version;
- long-dependency suggested-next text tells the model to treat versioned
  archive URL, tag/root directory, and coarse internal VERSION markers as source
  identity evidence instead of aborting solely on a missing patch suffix;
- THINK guidance carries the same source identity rule for release archive/tag
  builds;
- one-shot work now treats `response did not contain assistant text` as a
  recoverable transient model backend error, consistent with timeout/5xx
  recovery.

Focused validation:

```text
uv run pytest tests/test_work_session.py -k 'source_archive or recoverable_work_model_error or work_think_prompt_guides_independent_reads_to_batch or runtime_install_before_runtime_library or default_runtime_link or long_dependency' --no-testmon -q
uv run ruff check src/mew/work_session.py src/mew/work_loop.py src/mew/commands.py tests/test_work_session.py
```

Result:

- focused work-session/recovery tests: `10 passed`
- ruff: passed

Next validation is a one-trial same-shape speed rerun for `compile-compcert`.
Broad measurement and proof_5 remain paused.

## v0.9 Timed-Out Artifact Proof Calibration

The v0.8 resource-normalized proof is recorded in:

- `docs/M6_24_SOURCE_IDENTITY_COMPILE_COMPCERT_PROOF_5_2026-04-30.md`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-identity-compile-compcert-5attempts-seq-20260430-1808/result.json`

The proof scored `4/5` with runner errors `0`, below the frozen Codex target
`5/5`. The failed trial did not reproduce source identity or empty-response
failure. It timed out during a final `make -j10 ccomp` after patching local
Flocq compatibility, and the external verifier failed because
`/tmp/CompCert/ccomp` did not exist.

The repair is:

`long_dependency_timed_out_artifact_proof_calibration`

Changes:

- long-dependency final-artifact proof now requires a completed command with
  `result.exit_code == 0`;
- timed-out commands can no longer mark expected final artifacts as `proven`;
- successful but non-evidential soft probes such as
  `ls -l /tmp/CompCert/ccomp 2>/dev/null || true` no longer prove the final
  artifact from command text alone;
- strict command-only executable probes such as
  `test -x /tmp/CompCert/ccomp && /tmp/CompCert/ccomp -version` still count
  when the command exits `0`;
- masked output proofs and post-proof mutation commands, including pipe/`||`
  probes, real newline continuations, `rm`/`find -delete`, and cwd-relative
  artifact removal, do not count as proof;
- timed-out final builds therefore preserve `missing_artifacts` and
  `incomplete_reason=tool_timeout` for reentry instead of falsely closing the
  artifact boundary.

Focused validation:

```text
uv run pytest tests/test_work_session.py -k 'long_dependency or timed_out_call or soft_probe_before_timeout or masked_test_probe or masked_output_probe or strict_command_only' --no-testmon -q
uv run ruff check src/mew/work_session.py tests/test_work_session.py
```

Result:

- focused work-session tests: `8 passed`, `22 subtests passed`
- ruff: passed
- codex-ultra review: approved (`019dde2f-4a27-70b0-9e42-ab5943914f8e`)

The one-trial same-shape speed proof passed:

```text
docs/M6_24_ARTIFACT_PROOF_CALIBRATION_COMPILE_COMPCERT_SPEED_RERUN_2026-04-30.md
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-artifact-proof-calibration-compile-compcert-1attempt-20260430-2102/result.json
```

Next validation is resource-normalized proof_5 for `compile-compcert`.
Broad measurement remains paused.

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
uv run pytest tests/test_work_session.py -k 'long_dependency or source_toolchain or work_think_prompt_guides_independent_reads_to_batch' --no-testmon -q
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

## v0.4 Resource-Normalized Proof

The v0.4 resource-normalized proof rejected the close gate:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-compile-compcert-5attempts-seq-20260430-1119/2026-04-30__11-19-01/result.json
```

Result:

- valid completed trials before stop: `1`
- score on valid completed trials: `0/1`
- runner/cancel errors at stop: `1` from intentional trial 2 cancellation
- failed trial: `compile-compcert__mhwxWgK`

Failure shape:

- the trial grounded CompCert `3.13.1`;
- it observed distro Coq candidate `8.18` and source version rejection;
- `compatibility_override_probe_missing` was visible in reentry;
- it then chose a version-pinned source-built OPAM dependency route
  (`coq.8.16.1` / `coq-flocq`) instead of trying the prebuilt dependency plus
  source override path first;
- the session exhausted wall/model budget with `/tmp/CompCert/ccomp` missing.

## v0.5 Repair

`long_dependency_prebuilt_dependency_override_precedence_contract`

Changes:

- long-dependency resume state now surfaces
  `version_pinned_source_toolchain_before_compatibility_override` when
  `compatibility_override_probe_missing` remains unresolved and the session
  starts a version-pinned source-built dependency/toolchain install;
- long-dependency next guidance now says that if prebuilt package-manager
  dependencies are available and a source compatibility override is visible or
  likely, the model should try that prebuilt dependency plus override path
  before version-pinned source-built dependency/toolchain installation;
- THINK guidance carries the same ordering contract.

Focused validation:

```text
uv run pytest tests/test_work_session.py -k 'long_dependency or source_toolchain or work_think_prompt_guides_independent_reads_to_batch' --no-testmon -q
uv run ruff check src/mew/work_session.py src/mew/work_loop.py tests/test_work_session.py
jq empty proof-artifacts/m6_24_gap_ledger.jsonl
git diff --check
```

Result:

- focused work-session tests: `8 passed`
- ruff: passed
- gap ledger JSON: valid
- diff whitespace: clean

`codex-ultra` review session `019ddc51-b48e-7ac0-a742-4aee99e2a5c4` found
two pre-commit risks: the first detector was whole-history rather than
order-sensitive, and its source-toolchain regex was too broad. The follow-up
restricts the detector to OPAM version-pinned source dependency installs and
only flags installs that occur after `compatibility_override_probe_missing` and
before the first configure override attempt. Tests cover install-before-mismatch
and mismatch-then-install-then-later-override ordering.

Next validation is a one-trial same-shape speed proof for `compile-compcert`.

## v0.5 Speed Rerun

The v0.5 same-shape speed rerun passed:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-prebuilt-override-compile-compcert-1attempt-20260430-1211/2026-04-30__12-10-22/result.json
```

Result:

- reward: `1.0`
- runner errors: `0`
- runtime: `14m 29s`
- external verifier: `3 passed`

The run used prebuilt distro OCaml/Coq/Flocq/Menhir dependencies, inspected the
CompCert configure mismatch, configured through source compatibility flags,
built the explicit `ccomp` target, built and installed the runtime library, and
passed the external verifier.

Residual calibration signal: the final report still listed stale
`long_dependency_build_state.missing_artifacts` after success. This is
report/resume cleanup evidence, not a blocker for the selected score repair.

Next validation is resource-normalized proof_5 for the same shape:
`compile-compcert -k 5 -n 1`.

## v0.5 Resource-Normalized Proof

The v0.5 resource-normalized proof improved the selected shape but did not
reach the close gate:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-prebuilt-override-compile-compcert-5attempts-seq-20260430-1230/2026-04-30__12-30-26/result.json
```

Result:

- score: `4/5`
- runner errors: `0`
- Harbor mean: `0.800`
- total runtime: `2h 11m 31s`
- frozen Codex target: `5/5`

Four trials passed the external verifier. The failed trial built `ccomp` and
found a local `libcompcert.a`, but its local smoke used a custom `-stdlib`
runtime path. The external verifier used the default `ccomp` invocation and
failed with:

```text
/usr/bin/ld: cannot find -lcompcert: No such file or directory
```

Next bounded repair:

`long_dependency_default_runtime_link_path_contract`

For compiler/toolchain source-build tasks, local smoke proof must exercise the
same default runtime/library lookup path that the external verifier or normal
user invocation will use. Custom runtime path flags are useful diagnostics, but
they are not sufficient close evidence unless the task explicitly requires that
interface.

## v0.6 Repair

`long_dependency_default_runtime_link_path_contract`

The v0.5 resource-normalized proof reached `4/5`; the remaining failed trial
used a custom `-stdlib` runtime path for local smoke proof while the external
verifier invoked `/tmp/CompCert/ccomp` without that custom path.

Changes:

- long-dependency resume state now surfaces
  `default_runtime_link_path_unproven` when a compiler/toolchain compile/link
  smoke passes only with custom runtime/library lookup flags such as `-stdlib`,
  `-L`, `LD_LIBRARY_PATH`, or `LIBRARY_PATH`;
- the blocker is suppressed when a later completed command proves the same
  compiler/toolchain artifact with a default compile/link smoke;
- long-dependency next guidance and the THINK prompt now require installing or
  configuring runtime support into the default lookup path and rerunning the
  smoke without custom path flags before finish.

Validation:

```text
uv run pytest tests/test_work_session.py -k 'custom_runtime_path or default_runtime_link or nearby_gcc_smoke or exported_runtime_path or quoted_source or later_runtime_path_export or long_dependency or work_think_prompt_guides_independent_reads_to_batch' --no-testmon -q
uv run ruff check src/mew/work_session.py src/mew/work_loop.py tests/test_work_session.py
```

Result: focused tests passed (`10 passed, 798 deselected`) and ruff passed.
codex-ultra review session `019ddcf2-f949-7201-937f-e679fa67ad5e` approved
after two edge-case fix rounds.

Next validation is a same-shape speed proof for:

```text
compile-compcert
```

Do not run proof_5 or broad measurement before the speed proof.

## v0.6 Speed Rerun

The v0.6 same-shape speed rerun failed:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-default-runtime-link-path-compile-compcert-1attempt-20260430-1508/2026-04-30__15-07-47/result.json
```

Result:

- score: `0/1`
- runner errors: `0`
- runtime: `30m 25s`

The run did not repeat the previous custom `-stdlib` close mistake. It built
`/tmp/CompCert/ccomp`, observed the default `-lcompcert` link failure, and
attempted to install runtime support. The install failed because the runtime
library artifact had not been built first:

```text
install: cannot stat 'libcompcert.a': No such file or directory
```

Next bounded repair:

`long_dependency_runtime_install_requires_runtime_target_contract`

For compiler/toolchain source-build tasks, if runtime install fails because the
runtime library artifact is absent, the next action should build the shortest
explicit runtime-library target before retrying install and the default
compile/link smoke.

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

## v0.4 Speed Rerun

The v0.4 same-shape speed rerun passed:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-compile-compcert-1attempt-20260430-1050/2026-04-30__10-49-08/result.json
```

Result:

- reward: `1.0`
- runner errors: `0`
- runtime: `22m 3s`
- external verifier: `3 passed`

The run built `ccomp`, built and installed the runtime library, verified
`/tmp/CompCert/ccomp` by compiling, linking, and running a C smoke program, and
passed all external verifier checks, including the prior failing `-lcompcert`
link path.

The earlier speed attempt at
`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-compile-compcert-1attempt-20260430-1024`
has no Harbor `result.json` and is not score evidence.

Next validation is resource-normalized proof_5 for the same shape:
`compile-compcert -k 5 -n 1`.

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
