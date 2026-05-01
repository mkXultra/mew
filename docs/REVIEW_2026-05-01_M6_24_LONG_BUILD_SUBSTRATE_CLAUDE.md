# Review 2026-05-01 - M6.24 Long-Build Substrate (claude slot)

Reviewer: claude (round-1, orchestrate-build-review)

Verdict: **APPROVE_WITH_CHANGES**

The substrate direction is right and the design respects the controller's
explicit non-goals (no CompCert solver, no second authoritative lane, no
weakening of `acceptance_done_gate_decision()`). The five typed concepts are
small enough for mew, the migration phasing is reviewable, and the
anti-accretion checklist correctly identifies what must stop happening.

But several load-bearing details are under-specified in ways that will either
silently regress current behavior in Phase 1, or force the implementer to
re-derive policy that should have been settled at design time. The fixes
below are required before Phase 0 implementation lands.

## Findings

### 1. (Major) `command_evidence` ref ids conflict with the existing integer-only ref coercer

The CommandEvidence example uses string ids such as
`"work_session:1:tool_call:9"` (DESIGN line 130). But
`src/mew/acceptance.py:790-793` (`_coerce_evidence_refs`) silently drops any
ref whose `id` cannot be cast to `int`:

```python
try:
    ref_id = int(raw_id)
except (TypeError, ValueError):
    continue
```

`_check_evidence_refs` and `_evidence_tool_ids` are also integer-only, and the
existing `kind` is hardcoded to `"tool_call"` at acceptance.py:1668. As written
the design's `{"kind": "command_evidence", "id": "work_session:1:tool_call:9"}`
ref shape would never resolve through the done gate.

Target: `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md` Core Concepts
> CommandEvidence and Backward Compatibility section.

Fix: choose one of (a) require integer-typed CommandEvidence ids and rewrite
the example, or (b) extend `_coerce_evidence_refs` (and
`_check_evidence_refs`) in Phase 0 to accept non-integer ids when
`kind == "command_evidence"`, with explicit per-kind validation. Either way,
call this out as an explicit Phase 0 deliverable in the migration plan and
add a parity test asserting that mixed `tool_call` + `command_evidence` refs
both resolve through `_evidence_ref_findings_for_checks()`.

### 2. (Major) Legacy projection contract is not specified field-by-field

DESIGN says (lines 691-695, 656-658) the reducer will project `LongBuildState`
back to `long_dependency_build_state` so existing consumers keep working. But
the current dict has nine populated fields (`progress`, `expected_artifacts`,
`missing_artifacts`, `latest_build_tool_call_id`, `latest_build_status`,
`latest_build_command`, `incomplete_reason`, `strategy_blockers`,
`suggested_next`) and `format_work_session_resume()` reads every one of them
(`work_session.py:10394-10442`). The design only sketches the projection key
and gives no per-field mapping rule.

Without an enumerated projection contract, Phase 1 will either:
- silently regress text rendered by `format_work_session_resume()` (which
  many existing tests assert against), or
- duplicate every existing detector inside the new reducer "for safety,"
  defeating the consolidation goal.

Target: DESIGN section "Layer Integration -> work_session.py" and Phase 1.

Fix: add a table mapping every current `long_dependency_build_state` field to
its source in `LongBuildState` / `BuildAttempt` / `RecoveryDecision`, and
state explicitly that the Phase 1 projection must produce byte-identical
`format_work_session_resume()` output for the existing CompCert-shaped
fixtures (i.e. the ~10 tests under
`tests/test_work_session.py::test_work_session_resume_*long_dependency*`).

### 3. (Major) Failure taxonomy lacks the explicit current-blocker mapping table

DESIGN section "Failure Taxonomy" lists 15 generic classes and gives one
example mapping (`runtime_library_subdir_target_path_invalid ->
build_system_target_surface_invalid`). The current code has at least 10
emitted blocker codes (visible in `work_session.py` and confirmed in tests):

- `dependency_generation_order_issue`
- `untargeted_full_project_build_for_specific_artifact`
- `external_dependency_source_provenance_unverified`
- `default_runtime_link_path_unproven`
- `default_runtime_link_path_failed`
- `runtime_install_before_runtime_library_build`
- `runtime_library_subdir_target_path_invalid`
- `external_branch_help_probe_too_narrow_before_source_toolchain`
- `compatibility_branch_budget_contract_missing`
- `vendored_dependency_patch_surgery_before_supported_branch`

Target: DESIGN "Failure Taxonomy" section.

Fix: add an explicit mapping table from each existing blocker code to a
generic `failure_class`, and note any blocker that intentionally does not
collapse (so the anti-accretion gate has a fixed reference). Mark which
mappings happen in Phase 1 (legacy projection) versus Phase 2
(`RecoveryDecision` derivation). Without this, Phase 2's "narrow subset" is
impossible to audit and the anti-accretion gate is unenforceable in
practice.

### 4. (Major) Phase 2 RecoveryDecision subset omits two recently-added blockers

Phase 2 names seven failure classes for `RecoveryDecision` derivation
(DESIGN lines 707-715), but does not include
`source_provided_branch_unchecked` (covers
`external_branch_help_probe_too_narrow_before_source_toolchain`) or
`vendored_dependency_surgery_too_early` (covers
`vendored_dependency_patch_surgery_before_supported_branch`). Both are in
the design's own failure taxonomy and are the two most recent v1.4/v1.6
repairs in the dossier.

Target: DESIGN "Migration Plan -> Phase 2".

Fix: either expand the Phase 2 subset to include both classes (preferred),
or explicitly state in the design why those two stay on the legacy
suggested-next paragraph through Phase 2 and which later phase converts
them. Otherwise the substrate will not actually shorten the
`LongDependencyProfile` prompt sentences for the most recent CompCert
repairs after Phase 2 lands.

### 5. (Major) Anti-accretion gate has no enforcement surface

The gate is a 10-question checklist plus a "static prompt sections should
trend down" rule (DESIGN lines 833-838). Today's
`prompt_section_metrics()` returns char counts and hashes but does not assert
budgets. There is no test, ledger entry requirement, or CI check that
actually blocks a profile-growing PR.

Target: DESIGN "Anti-Accretion Gate" section.

Fix: commit to one concrete enforcement surface, e.g.
- a unit test that asserts
  `len(LongDependencyProfile.content) <= snapshot_chars + N`, with the
  snapshot updated only when an entry is added to a named ledger file, or
- a JSON record under `proof-artifacts/` that pins each section's hash and
  fails the test on hash change without a paired ledger entry, or
- a CI-style check in `tests/test_prompt_sections.py` that diff-asserts
  static-section hashes per migration phase.

The current "should trend down" wording is the same kind of prose policy the
design is trying to retire.

### 6. (Major) `runtime_proof.required = "when_toolchain_or_compiler"` reuses an unspecified classifier

`LongBuildContract.runtime_proof.required` is conditional on toolchain /
compiler tasks, but the design never defines who decides that. Today
`is_long_dependency_toolchain_build_task()` decides and uses
marker-based heuristics that are themselves CompCert-shaped (see
`acceptance.py:1217-1221` plus `_LONG_DEPENDENCY_BUILD_*_MARKERS`). If
`LongBuildContract` inherits the same classifier, the substrate is generic
in name only — `runtime_proof` will fire on the same tasks and miss the
same tasks as today.

Target: DESIGN "Core Concepts -> LongBuildContract -> runtime_proof".

Fix: state explicitly which mechanism decides `runtime_proof.required` —
task-text classifier, model-declared, or both with provenance — and confirm
that at least one transfer fixture (the design lists
`rust_or_cargo_cli_long_build` and `python_native_extension_cli`) exercises
the negative case where `runtime_proof.required = "not_required"`. Without
this, Phase 2's `runtime_default_path_unproven` derivation will overfit to
toolchain shapes that look like CompCert.

### 7. (Minor) Resume-dict surface during migration is unspecified

DESIGN says `LongBuildState` becomes the source of truth and
`long_dependency_build_state` becomes a projection, but does not say
whether the new typed state is exposed in `resume["long_build_state"]`
during migration, or only inside the legacy projection key.
`work_session.py:10149` and `work_loop.py:6269` both index
`resume["long_dependency_build_state"]` today, and the prompt's
`DynamicFailureEvidence` flag `has_long_dependency_build_state` would need
either a new flag or a renamed flag if the new key replaces the old.

Target: DESIGN "Layer Integration -> work_session.py" and
"Backward Compatibility".

Fix: state explicitly whether the migration-period resume dict carries
both keys, and (if both) at which phase the legacy key is removed. If only
the legacy key is exposed, document that and state how prompt rendering in
work_loop.py reaches the typed state (passed separately, derived again, or
both).

### 8. (Minor) `suggested_next` replacement is the highest-risk piece and the design only describes it abstractly

The current `suggested_next` is a 36-line static paragraph
(`work_session.py:5680-5715`) covering seven distinct recovery branches.
DESIGN section "Prompt Policy After Consolidation" says the prompt should
render "current failure class / next allowed recovery action / prohibited
repeated action" but does not show a single worked example for an existing
failure class. The handoff explicitly flags this as the highest-risk claim
to review and the design defers the answer to implementation.

Target: DESIGN "Prompt Policy After Consolidation".

Fix: include one worked before/after example. For example, what does
`runtime_link_failed` render to today (one sentence cut from the legacy
paragraph) and what does the post-Phase-2 dynamic `RecoveryDecision`
rendering look like for the same failure class? This anchors the Phase 2
review and tells the implementer how short the dynamic block must stay.

### 9. (Minor) Schema versioning policy is undefined

Each typed object includes `schema_version: 1` but the design never says:
- the bump rule (additive vs breaking),
- whether mixed v1/v2 records are allowed within one work session,
- whether the legacy projection tracks its own version.

For a substrate intended to outlive multiple migrations and be cited by
acceptance evidence, this is load-bearing.

Target: DESIGN "Core Concepts" preamble.

Fix: add one paragraph stating the version-bump rule (additive only without
bump; field type or semantic change requires bump), and whether the legacy
projection key carries an independent version.

### 10. (Minor) `RecoveryDecision.budget.max_attempts_for_failure_class = 2` is an ungrounded constant

DESIGN line 360 hardcodes `max_attempts_for_failure_class: 2` with no
discussion of its relationship to the existing
`WORK_WALL_LONG_TOOL_RECOVERY_RESERVE_SECONDS = 60.0` and
`WORK_WALL_LONG_TOOL_RECOVERY_MIN_TIMEOUT_SECONDS = 600.0` budgets in
`commands.py:343-345`. Phase 4 says "keep current constants unless tests
prove a threshold needs adjustment" (line 754) — but two-attempts-per-class
is a new constant introduced by this design.

Target: DESIGN "Core Concepts -> RecoveryDecision".

Fix: state whether `max_attempts_for_failure_class` is per-stage,
per-attempt-id, or per-evidence-id; whether it counts only failed attempts
or also includes successful-but-still-blocked attempts; and how it
interacts with `wall_seconds` budget exhaustion. Or remove the example
constant and state explicitly that the threshold is set by Phase 2 tests.

### 11. (Minor) `CommandEvidence.source = "command_event"` is undefined

DESIGN line 132 lists three sources: `tool_call|command_event|legacy_tool_call`.
Only `tool_call` (current) and `legacy_tool_call` (Phase 0 synthesis path)
are described elsewhere. `command_event` appears in no other section and
has no meaning in the migration plan.

Target: DESIGN "Core Concepts -> CommandEvidence".

Fix: either define `command_event` (probably the Phase 3 native record) or
remove it from the source enum.

### 12. (Minor) Validation Strategy does not commit to projection-parity tests

The validation strategy (DESIGN lines 851-857) lists "Legacy
`long_dependency_build_state` projection compatibility" as one required test
group, but does not state the parity standard (byte-identical projected
dict? semantic equality? identical
`format_work_session_resume()` substring assertions?).

Target: DESIGN "Validation Strategy -> Unit and Reducer Tests".

Fix: add an explicit parity rule. Recommend: "every existing
`tests/test_work_session.py::test_work_session_resume_*long_dependency*`
test must continue to pass without modification through Phase 1 and Phase 2
of the migration; phase-3 changes that alter resume text must update those
tests in the same patch with the same assertion structure."

## Open Questions (advisory, not gating)

- Should `LongBuildContract` ever be model-supplied (so a task can declare
  its required artifacts and runtime-proof requirement explicitly)? The
  design treats it as parser-derived, which preserves determinism but
  inherits the same task-classifier overfitting.
- Is `BuildAttempt.id` strictly per-tool-call, or can a `make depend && make
  ccomp` chain produce two attempts? The design says "one attempt should
  normally correspond to one command tool call" but the Open Questions list
  asks the same thing without resolving it. Phase 1 needs the answer.
- The transfer fixtures list five candidates but none exercises a
  `default_smoke = not_required` toolchain (e.g. a build that produces a
  shared library consumed only by another build step). Worth adding.

## Implementation Risk Notes

- Phase 1 is where the design will succeed or silently regress. The legacy
  projection contract (Finding 2) and the failure-taxonomy mapping
  (Finding 3) are the two artifacts that must exist before code lands;
  without them, the same detector logic moves into a new module and nothing
  shrinks.
- Phase 4 (budget enforcement from `RecoveryDecision`) replaces the
  marker-based heuristic in `work_tool_recovery_reserve_seconds()`
  (commands.py:6154-6201). That function currently gates on text markers
  including `"libcompcert"` (commands.py:6150). Migration must explicitly
  delete the CompCert-shaped marker, not just bypass it; otherwise the
  CompCert overfit silently survives.
- The anti-accretion gate (Finding 5) is only as strong as its enforcement
  surface. If the team accepts the gate as a checklist only, expect the
  next CompCert miss to attempt a 16th sentence in `LongDependencyProfile`.

## Verification Summary

- Read the design end-to-end (DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md).
- Read all four required prerequisite reviews
  (LONG_DEPENDENCY_REFERENCE_DIVERGENCE, CODEX_LONG_DEPENDENCY_AUDIT,
  CLAUDE_CODE_LONG_DEPENDENCY_AUDIT, MEW_LONG_DEPENDENCY_DIVERGENCE) and the
  controller dossier / decision ledger / gap improvement loop.
- Inspected `src/mew/work_session.py` (notably
  `build_long_dependency_build_state` lines 5486-5717 and
  `format_work_session_resume` lines 10394-10442),
  `src/mew/work_loop.py` prompt-section assembly (lines 6160-6455 and the
  span markers at 6223-6238), `src/mew/commands.py` budget code
  (lines 343-347 and 6154-6253),
  `src/mew/acceptance.py` evidence-ref coercion (lines 775-801 and
  1651-1671) plus done gate (line 2631+),
  `src/mew/acceptance_evidence.py` shape (lines 1-122),
  `src/mew/prompt_sections.py` metrics surface, and a sample of
  `tests/test_work_session.py` long-dependency assertions
  (lines 4639-4750+).
- No source code modified; this is a docs-only review.
