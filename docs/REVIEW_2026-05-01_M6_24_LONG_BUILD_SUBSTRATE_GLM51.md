# Review: M6.24 Long-Build Substrate Design (GLM-5.1 Slot)

Date: 2026-05-01

Reviewer: glm5.1 slot

Inputs reviewed:
- `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`
- `.codex-artifacts/orchestrate-build-review/m6_24_long_build_substrate/round-1/builder/handoff.md`
- `docs/REVIEW_2026-05-01_M6_24_LONG_DEPENDENCY_REFERENCE_DIVERGENCE.md`
- `docs/REVIEW_2026-05-01_M6_24_CODEX_LONG_DEPENDENCY_AUDIT.md`
- `docs/REVIEW_2026-05-01_M6_24_CLAUDE_CODE_LONG_DEPENDENCY_AUDIT.md`
- `docs/REVIEW_2026-05-01_M6_24_MEW_LONG_DEPENDENCY_DIVERGENCE.md`

Source inspected:
- `src/mew/work_session.py` (full)
- `src/mew/work_loop.py` (full)
- `src/mew/commands.py` (full)
- `src/mew/acceptance.py` (full)
- `src/mew/acceptance_evidence.py` (full)
- `src/mew/prompt_sections.py` (full)

## Verdict: APPROVE_WITH_CHANGES

The design is well-scoped, mew-sized, and correctly targets the right abstraction layer. It addresses the core problem identified by all four input reports: operational facts scattered across prompt prose, transcript-derived detectors, resume text, and external ledgers. The five core concepts (CommandEvidence, LongBuildContract, BuildAttempt, LongBuildState, RecoveryDecision) are correctly bounded and the migration plan is appropriately phased.

However, several findings require fixes before implementation to avoid subtle regressions and design gaps.

## Findings

### Major 1: CommandEvidence synthesis must define precedence for `command` field extraction

**Target:** `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md` - Backward Compatibility, rule 3

**Problem:** The design says to synthesize `command` from `result.command || parameters.command || parameters.verify_command` but does not specify which takes precedence when multiple are present. Looking at `acceptance_evidence.py:82`, `tool_call_command_text()` uses the order `result.command || parameters.command || parameters.verify_command`. However, `work_session.py` line references show that `parameters.command` is the primary command and `parameters.verify_command` is a write-tool verification field, not a build command. If a write_file with verify_command is mistakenly synthesized as a build command, the reducer will misclassify it.

**Fix:** Add an explicit precedence rule: only synthesize CommandEvidence for `tool_call` records where `tool in {"run_command", "run_tests"}`. For write tools, skip synthesis or synthesize with `source = "legacy_write_tool"` and `tool = "write_file"` rather than `run_command`. State this as a rule in the design.

### Major 2: LongBuildState stages lack a `not_required` sentinel for stages conditional on contract policy

**Target:** `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md` - LongBuildState stages

**Problem:** Only `runtime_built`, `runtime_installed_default`, and `default_smoke` have `not_required` as a status. But `configured` and `dependencies_generated` may also be not required for builds that use a simpler build system. The design explicitly mentions a `rust_or_cargo_cli_long_build` transfer fixture with "no runtime link requirement," but does not account for source builds that skip configure or dependency generation entirely (e.g., a single-file C compile). If the reducer forces these to `unknown` when they are genuinely not applicable, the state machine will report `in_progress` indefinitely for stages the contract does not require.

**Fix:** Either (a) add `not_required` as a valid status for all stages with a gating condition like `"when contract.build_policy.dependency_generation_before_final_target is false"` or (b) explicitly state that the reducer should only track stages relevant to the contract and omit irrelevant stage keys entirely. Option (b) is cleaner; state that `LongBuildState.stages` is populated based on contract requirements, not a fixed enumeration.

### Major 3: RecoveryDecision.decision enum conflates recovery action with completion policy

**Target:** `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md` - RecoveryDecision

**Problem:** The `decision` field values are `continue|block_for_budget|ask_user|finish_not_allowed`. The first two are recovery actions, `ask_user` is an escalation action, and `finish_not_allowed` is an acceptance gating concern. But `finish_not_allowed` overlaps with `acceptance_done_gate_decision()`. If `RecoveryDecision.decision == finish_not_allowed`, the design says this is separate from the done gate, but the work loop may produce contradictory signals: RecoveryDecision says "you can't finish" while the done gate also says "you can't finish" for different reasons. The design needs to clarify whether `finish_not_allowed` is advisory (redundant with the done gate) or whether it gates the model's ability to emit `task_done=true` before the done gate is consulted.

**Fix:** Remove `finish_not_allowed` from `RecoveryDecision.decision`. RecoveryDecision should only produce recovery actions: `continue`, `block_for_budget`, `ask_user`. The done gate remains the sole authority on whether completion is allowed. If recovery state is blocked but the done gate would allow completion, the done gate wins. This avoids dual authority.

### Major 4: The failure taxonomy includes `model_format_transient` which is not a long-build failure class

**Target:** `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md` - Failure Taxonomy

**Problem:** `model_format_transient` is a model-level error (malformed model response), not a build execution failure. Including it in the long-build failure taxonomy scopes the reducer too broadly. The reducer processes `CommandEvidence` from tool calls; model format errors are not command evidence. If the reducer must handle model errors, that scope belongs to the work loop's retry/recovery, not the build substrate.

**Fix:** Remove `model_format_transient` from the failure taxonomy. State that model-level retry/recovery remains in `work_loop.py` and is not part of the long-build substrate. If model errors need typed state later, that should be a separate design.

### Minor 1: The `env_summary` field on CommandEvidence should clarify truncation/privacy boundaries

**Target:** `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md` - CommandEvidence

**Problem:** The design includes `env_summary: {}` but does not state what goes in it or how sensitive values are handled. Mew already has `is_sensitive_path()` in read_tools and various privacy-aware patterns. If `env_summary` records environment variables that contain tokens or keys, this could leak credentials into resume state and prompt text.

**Fix:** Add a note that `env_summary` should only record environment variable names (not values), or a bounded whitelist of safe values (e.g., `CC`, `CXX`, `PATH` without the actual content, `MAKEFLAGS`). Alternatively, state that `env_summary` is deferred to Phase 3+ and remains `{}` in Phase 0.

### Minor 2: The anti-accretion gate should specify who records the answers and where

**Target:** `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md` - Anti-Accretion Gate

**Problem:** The gate says answers must be "recorded in the design note, repair note, or decision ledger" but does not specify a canonical location or format. The M6.24 decision ledger already has a specific format (`docs/M6_24_DECISION_LEDGER.md`). If each gate answer is scattered across different files with different formats, the gate becomes unenforceable in practice.

**Fix:** Add a concrete requirement: anti-accretion gate records should be appended to `docs/M6_24_DECISION_LEDGER.md` under a dedicated `anti_accretion_gate` heading with the 10 questions as structured fields. This makes gate compliance auditable.

### Minor 3: Transfer fixtures lack a "build with no source authority" negative case

**Target:** `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md` - Transfer Fixtures

**Problem:** The five proposed transfer fixtures all cover positive build scenarios. None tests what happens when the source authority check fails (e.g., a build that starts from an unverified tarball). The `source_authority_unverified` failure class is listed in the taxonomy but has no corresponding fixture.

**Fix:** Add a sixth fixture: `unverified_source_build_rejected` where a source build attempts to proceed from an unverified download and the reducer correctly classifies the failure as `source_authority_unverified`. This validates that the contract's `source_policy.authority_required` is enforced, not just documented.

## Open Questions

1. **BuildAttempt 1:1 with tool calls in v1:** The design says "one attempt should normally correspond to one command tool call" but does not say what happens when a compound command (`make dep && make all`) produces different failure classes in each segment. Should the reducer classify at the segment level or the command level in Phase 0? The current `acceptance_evidence.py` already segments compound commands (`split_unquoted_shell_command_segments`), so the reducer could leverage that.

2. **Contract extraction determinism:** The design says `LongBuildContract` is "extracted from task text, action acceptance checks, and possibly model-provided working memory." The "possibly model-provided working memory" clause introduces nondeterminism. The design should state whether contract extraction must be deterministic (rerunnable on resume without model input) or whether model-provided contract fields are allowed to change between sessions.

3. **Legacy projection staleness window:** Rule 4 says "Keep `work_session.resume.long_dependency_build_state` during migration as a projection of `LongBuildState`." For how long? Until Phase 5? Until all tests pass? The design should state an explicit removal condition or a bounded migration window.

## Implementation Risk Notes

- **Highest risk:** Phase 1 (contract extraction and state projection) must preserve byte-identical `long_dependency_build_state` output for existing test fixtures. Any deviation in blocker codes, suggested_next text, or artifact lists will break golden tests. Recommend a regression test suite that snapshots the full `long_dependency_build_state` output for all existing CompCert-shaped fixtures before Phase 1 changes.

- **Medium risk:** The reducer classification accuracy for failure taxonomy depends on the quality of the synthesized `CommandEvidence`. If `exit_code`, `timed_out`, or `command` fields are incorrectly synthesized from old tool_calls, the reducer will produce wrong failure classes. Phase 0 parity tests must cover edge cases: timed-out calls with `exit_code=0`, interrupted calls, and calls where `result.command` differs from `parameters.command`.

- **Low risk:** The transfer fixtures may inadvertently encode CompCert-shaped assumptions (e.g., using `/tmp/` paths, Make-based builds). The design's explicit naming and diversity requirements mitigate this, but the review should check fixture PRs against the anti-accretion gate.

## Summary

The design is the right next step for M6.24. It correctly identifies that the current approach has reached diminishing returns through prompt/detector accretion, and proposes a typed reducer with appropriate backward compatibility. The four major findings are fixable in the design document without changing the overall architecture. After these fixes, implementation should proceed from Phase 0.
