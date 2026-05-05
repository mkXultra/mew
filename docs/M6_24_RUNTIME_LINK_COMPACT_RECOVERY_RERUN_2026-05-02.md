# M6.24 Runtime-Link Compact Recovery Rerun - 2026-05-02

## Trigger

Same-shape `compile-compcert` speed rerun after the config/source-script
external-hook evidence repair:

- Job:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-config-external-hook-compile-compcert-1attempt-20260502-2136`
- Trial: `compile-compcert__wU3DaVz`
- Harbor trials: `1`
- Runner errors: `0`
- Harbor mean reward: `0.0`
- Runtime: about `30m27s`
- `mew-report.work_exit_code`: `1`
- `work_report.stop_reason`: `wall_timeout`

The external verifier observed `/tmp/CompCert/ccomp`, but failed the default
functional smoke because the runtime library was not in the default link path:

- `test_compcert_exists_and_executable`: passed
- `test_compcert_rejects_unsupported_feature`: passed
- `test_compcert_valid_and_functional`: failed with
  `/usr/bin/ld: cannot find -lcompcert: No such file or directory`

## What The Run Actually Tested

This moved past the prior config/source-script external-hook regression:

1. A valid source archive was selected and extracted.
2. Source-provided external Flocq/MenhirLib branches were attempted.
3. `-ignore-coq-version` was discovered and applied.
4. `make depend` was eventually run before `make ccomp`.
5. The run built enough for `/tmp/CompCert/ccomp` to exist at verifier time.

The failure is therefore not a source acquisition, external branch, dependency
generation, or long-command continuation failure. The generic blocker is that a
runtime/default-link repair was selected too late, then compact recovery still
spent low remaining wall time on a large model turn.

## Observed Recovery Shape

After command step 6:

- `resume.long_build_state.current_failure.failure_class=runtime_link_failed`
- `legacy_code=default_runtime_link_path_failed`
- `allowed_next_action.stage=runtime_build_or_install`
- `allowed_next_action.required_evidence=terminal_success_default_runtime_smoke`
- `long_command_runs=[]`

The following model turns all timed out:

- step 7: compact recovery prompt about `59,967` chars, model timeout about
  `58.7s`
- step 8: compact recovery prompt about `54,917` chars, model timeout about
  `28.6s`
- step 9: compact recovery prompt about `54,917` chars, model timeout about
  `13.8s`
- step 10: compact recovery prompt about `54,916` chars, model timeout about
  `6.45s`

The prompt was nominally in `compact_recovery`, but it still included broad
source/dependency sections and a large dynamic Context JSON. That is too large
for a known runtime-link repair under shrinking wall time.

## Classification

Primary class:
`runtime_link_low_wall_compact_recovery_oversized`.

Stable selected gap:
`long_dependency_toolchain_build_strategy_contract`.

Layer:
model-context budgeting / prompt section routing, not task-specific solver.

This is a narrower recurrence of the earlier low-wall runtime-link recovery
class. It should not be fixed by adding a CompCert-specific command recipe.

## Repair

The bounded repair keeps the change generic:

- When compact recovery has a long-build `recovery_decision`, focus resume on
  the recovery contract and omit large unrelated resume fields such as command
  history, failures, unresolved failure payloads, and verifier agendas.
- When the current long-build recovery class is runtime-link/default-runtime
  related, do not re-inject broad source-acquisition and long-dependency prompt
  sections. Keep `RuntimeLinkProof`, `RecoveryBudget`, schema, compact recovery
  instructions, dynamic failure evidence, and the reduced Context JSON.
- For `runtime_link_failed`, the recovery prerequisite is now the concrete fact
  that the artifact was invoked by the failed default smoke, not a fully
  accepted final artifact proof. Final artifact proof remains required before
  finish.

## Validation

- Focused compact/runtime recovery subset:
  - `uv run pytest -q tests/test_work_session.py -k 'compact_recovery_resume_focuses_long_build_recovery_decision or compact_recovery_runtime_link_prompt_omits_source_rediscovery_sections or compact_recovery_context_hard_caps_long_build_payloads or long_build_recovery_command_can_spend_reserved_budget_after_linker_failure' --no-testmon`
  - `4 passed, 875 deselected`
- Broader long-build/work-session/acceptance subset:
  - `uv run pytest -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py -k 'long_build or long_dependency or runtime_link or compact_recovery or recovery_budget or default_smoke' --no-testmon`
  - `302 passed, 965 deselected, 22 subtests`
- Scoped Ruff:
  - `uv run ruff check src/mew/work_loop.py src/mew/long_build_substrate.py tests/test_work_session.py`
  - passed
- Gap ledger JSONL parse and diff check:
  - passed
- codex-ultra review:
  - `docs/REVIEW_2026-05-02_M6_24_RUNTIME_LINK_COMPACT_RECOVERY_CODEX.md`
  - final `STATUS: APPROVE`

## Next

Run exactly one same-shape `compile-compcert` speed_1. Do not run `proof_5` or
broad measurement before that rerun records a clean pass or a newer narrower
gap.
