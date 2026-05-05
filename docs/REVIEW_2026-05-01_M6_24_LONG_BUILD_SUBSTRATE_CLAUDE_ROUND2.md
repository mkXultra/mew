# Review 2026-05-01 - M6.24 Long-Build Substrate (claude slot, round 2)

Reviewer: claude (round-2, orchestrate-build-review)

Verdict: **APPROVE**

The revised design substantively addresses every accepted round-1 finding
and the merged-findings.yaml inventory. The flag-day cutover is clean,
deterministic acceptance evidence stays the final authority, the failure
taxonomy now carries an explicit current-blocker inventory, the
anti-accretion gate has a concrete enforcement surface, and `RecoveryDecision`
is correctly scoped to recovery actions only. What remains are
implementation-time questions that belong in Phase 0/1 work rather than the
design.

## Round-1 Finding Disposition

| # | Round-1 finding | Severity | Round-2 status |
| --- | --- | --- | --- |
| 1 | `command_evidence` ref ids vs integer coercer | Major | Fixed: ids are integers (line 133); refs are `{kind: command_evidence, id: N}` (line 134); design states "String ids are not used in v1 because acceptance evidence resolution needs a small deterministic lookup table" (line 174). |
| 2 | Legacy projection contract not specified | Major | Resolved by cutover: the legacy projection requirement is removed entirely (Flag-Day Cutover, lines 767-804); behavior/safety parity replaces byte parity. |
| 3 | Failure taxonomy mapping table missing | Major | Fixed: full inventory table at lines 657-677 covers all 10+ existing blocker codes plus the timed-out / masked / missing-artifact families, each with generic class and clear condition. |
| 4 | Phase 2 RecoveryDecision subset omits two recent blockers | Major | Resolved per merged-findings reframing: `source_provided_branch_unchecked` and `vendored_dependency_surgery_too_early` are now in the inventory and reducer state path; whether they get a Phase 3 RecoveryDecision is now an implementation choice — the dynamic state can render `failure_class + clear_condition` even without a RecoveryDecision. |
| 5 | Anti-accretion gate has no enforcement surface | Major | Fixed: lines 1013-1034 add metric/hash snapshot test, machine-readable ledger record with explicit fields, paired-fixture requirement, and Phase 5 to land the enforcement. |
| 6 | `runtime_proof.required` classifier undefined | Major | Fixed: explicit "Runtime proof classifier" section (lines 312-326), versioned as `runtime_proof_classifier_v1`, with positive and negative trigger rules. Negative fixture `non_toolchain_runtime_not_required` exists. |
| 7 | Resume-dict surface during migration unspecified | Minor | Resolved by cutover: old `long_dependency_build_state` dict is removed (Phase 2); new `long_build_state` shape replaces it. |
| 8 | `suggested_next` replacement not worked out | Minor | Adequately addressed by the dynamic prompt template (lines 737-746) plus the inventory's per-blocker clear conditions. A worked before/after example would still help Phase 2 reviewers, but is no longer a hard blocker. |
| 9 | Schema version policy undefined | Minor | Fixed: Phase 0 defines additive vs breaking rule and the cutover-rejects-mixed-version policy (lines 821-828). |
| 10 | `max_attempts_for_failure_class = 2` ungrounded | Minor | Not addressed; constant remains at line 461 with no semantics discussion. See Remaining Minor Issues below. |
| 11 | `CommandEvidence.source = command_event` undefined | Minor | Fixed: source enum is now `native_command|synthesized_fixture` (line 136); both are defined in Synthesis Scope. |
| 12 | Validation strategy projection-parity rule | Minor | Resolved by cutover: byte-identical parity is explicitly replaced with behavior/safety parity (Validation Strategy line 1055; Flag-Day Cutover lines 796-804). |

## Merged-Findings Disposition

All 10 accepted merged findings are addressed:

- **command-evidence-ref-ordering-and-scope** — Ordering/freshness section (lines 179-189), synthesis scope rules (lines 190-201), env privacy (lines 203-211).
- **long-build-contract-authority-and-runtime-classifier** — Authority precedence section (lines 286-310), source authority hierarchy (lines 301-310), runtime proof classifier (lines 312-326).
- **flag-day-cutover-not-legacy-projection** — Flag-Day Cutover section (lines 767-804) replaces compatibility with safety/behavior parity.
- **current-blocker-to-failure-class-inventory** — Inventory table (lines 655-679).
- **recovery-decision-scope-and-recent-blockers** — RecoveryDecision scope boundary (lines 430-434), decision enum reduced to `continue|block_for_budget|ask_user` (line 463), `model_format_transient` removed from taxonomy.
- **anti-accretion-enforcement** — Concrete enforcement surface (lines 1013-1034) + Phase 5.
- **contract-driven-stages** — Stage policy (lines 414-423); stages are now array-of-objects with `required: true|false` and `status: not_required` (lines 382-386).
- **migration-tests-not-byte-compat** — Behavior/safety parity language (Flag-Day Cutover) replaces byte compatibility.
- **schema-version-and-env-privacy** — Phase 0 policy + env_summary policy (lines 203-211, 821-828).
- **transfer-fixtures-negative-cases** — Five negative fixtures added (lines 1080-1093): `unverified_source_build_rejected`, `non_toolchain_runtime_not_required`, `write_verify_command_not_command_evidence`, `stale_artifact_after_mutation_rejected`, `masked_or_spoofed_artifact_proof_rejected`.

## Cutover Safety

The flag-day decision is cleanly bounded:

- Old `tool_call` final evidence refs are explicitly deferred (Deferred section, line 1138) — they remain valid for UI/debugging but stop being canonical for long-build proof.
- Old `long_dependency_build_state` resume dict and old blocker dicts are explicitly removable (Cutover lines 774-776).
- Active old sessions may need a fresh proof command rather than seamless resume (line 779-781) — the design accepts this.
- Historical docs and ledgers remain as audit records (line 782-783) — no rewrite required.
- All safety invariants are preserved: terminal-success, timeout/masked/spoofed/path-prefix rejection, post-proof mutation guard, wall/recovery budget, and `acceptance_done_gate_decision()` authority (lines 785-794).

The cutover is the right call given mew is unreleased; it removes a class of "preserve every old shape" complexity without weakening any safety check.

## Acceptance Evidence and Done-Gate Authority

Preserved and slightly strengthened:

- Final artifact freshness now considers source-tree and runtime/default-link search-path mutations (lines 184-186), tightening current behavior. This is intentional and the validation strategy includes ordering/freshness tests (line 1061).
- `RecoveryDecision` is explicitly recovery-only (lines 430-434); it cannot mark acceptance complete (line 473). The done gate keeps sole authority.
- Synthesis cannot promote write-tool `verify_command` or dry-run approvals into `CommandEvidence` (lines 199-201), with a paired negative fixture.
- `command_evidence` ref kind is now first-class; `evidence_kinds: ["command_evidence"]` (line 274) is the canonical final-proof evidence kind after cutover.

## Remaining Minor Issues (advisory, not gating)

These are Phase 0/1 implementation-time questions that the design correctly leaves open or under-specifies. None blocks the design.

1. `max_attempts_for_failure_class: 2` (line 461) still has no semantics discussion. Phase 0 / Phase 3 should define whether the counter is per-stage, per-failure-class-within-an-attempt-chain, or per-`evidence_id`; whether failed-only or also blocked-but-successful attempts count; and how it interacts with `wall_seconds` budget exhaustion. Either resolve in implementation or amend the design when Phase 3 lands.

2. The text-citation regex `_TOOL_ID_RE` at `src/mew/acceptance.py:45` matches only `tool[ call] #N`. The design says "Textual evidence may also say `command #N`" (line 173) but no Phase deliverable explicitly names extending the regex. Phase 1 should either (a) extend `_TOOL_ID_RE` to also match `command #N`, or (b) state that text-based citation is no longer load-bearing because the model writes structured `evidence_refs` dicts only. A small ambiguity, easy to settle at implementation.

3. Open Questions list (lines 1141-1158) keeps "Where should native `CommandEvidence` be stored after cutover" open. Phase 1 needs an answer because acceptance proof helpers (`long_dependency_artifact_proven_by_call` and friends) currently look up records via `_any_tool_call_by_id(session, tool_id)`. Whether `command_evidence` lives at `session["command_evidence"]`, inside `tool_calls`, or both, is a load-bearing Phase 1 wiring choice. Acceptable as a design open question; flag for Phase 1 plan.

4. Phase 1 cutover changes the canonical acceptance evidence path before Phase 2 replaces the resume state. During the Phase 1 → Phase 2 window, the resume dict still emits the old `long_dependency_build_state` while acceptance accepts only `command_evidence` refs. This is internally consistent (per cutover) but worth calling out so test fixtures stay in lockstep with phase landing.

## Implementation Risk Notes

- Phase 1's freshness tightening (search-path and source-tree mutation now invalidates proof) may regress some currently-passing fixtures. The tightening is intentional but Phase 1 tests should explicitly distinguish proof-relevant from proof-irrelevant mutations.
- Phase 5 (anti-accretion enforcement) may land before Phase 4 per the design; that flexibility is good. The hash/metric snapshot test should be authored against the Phase 2/3 prompt-section sizes, not the current legacy-prose sizes, otherwise it will lock in today's bloat.
- The CompCert-shaped marker in `commands.py` (`work_tool_recovery_reserve_seconds()` line 6150 references `"libcompcert"`) is a Phase 4 deletion target. The migration plan correctly aims to replace it with contract/state/recovery logic; the deletion should be explicit, not just bypassed.

## Verification Summary

- Read the revised design end-to-end (`docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`, 1198 lines).
- Read the round-2 builder handoff
  (`.codex-artifacts/orchestrate-build-review/m6_24_long_build_substrate/round-2/builder/handoff.md`).
- Read the round-1 merged findings
  (`.codex-artifacts/orchestrate-build-review/m6_24_long_build_substrate/round-1/merged-findings.yaml`).
- Read my prior round-1 review
  (`docs/REVIEW_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE_CLAUDE.md`).
- Spot-checked `src/mew/acceptance.py` regex (`_TOOL_ID_RE` line 45) and
  ref coercion (lines 775-801) to confirm integer-id strategy now aligns
  with existing code paths.
- No source code modified; this is a docs-only review.

## Bottom Line

The design is implementable as written. The cutover decision plus the failure-
class inventory plus the concrete anti-accretion enforcement together close
the substantive risks I raised in round 1. Phase 0 can begin.
