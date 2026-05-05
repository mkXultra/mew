# Review: M6.24 Long-Build Substrate Design - Round 2 (GLM-5.1 Slot)

Date: 2026-05-01

Reviewer: glm5.1 slot (round 2)

Inputs reviewed:
- `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md` (revised)
- `.codex-artifacts/orchestrate-build-review/m6_24_long_build_substrate/round-2/builder/handoff.md`
- `.codex-artifacts/orchestrate-build-review/m6_24_long_build_substrate/round-1/merged-findings.yaml`
- Prior review: `docs/REVIEW_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE_GLM51.md`

## Verdict: APPROVE

All accepted round-1 findings have been addressed. The flag-day cutover is cleanly bounded. Deterministic acceptance evidence and done-gate authority are preserved. Core concepts are precise enough for Phase 0 implementation. No remaining must-fix issues found.

## Round-1 Finding Disposition

### My findings (glm5.1 round 1)

| Finding | Disposition | Evidence in revised design |
| --- | --- | --- |
| Major 1: CommandEvidence synthesis scope | Fixed | Lines 192-201: synthesis restricted to `run_command`/`run_tests`; write tools and `verify_command` explicitly excluded. Fixture `write_verify_command_not_command_evidence` validates this. |
| Major 2: Contract-driven stages | Fixed | Lines 414-423: stages are contract-driven, irrelevant stages omitted. Lines 686-691: explicit policy. Example at line 383-385 shows `required: false, status: "not_required"`. |
| Major 3: RecoveryDecision scope | Fixed | Lines 430-433: scope boundary explicitly excludes finish decisions and model-format recovery. Line 463: decision enum is `continue|block_for_budget|ask_user` only. Line 473: "Never mark acceptance complete." |
| Major 4: model_format_transient removed | Fixed | Absent from failure taxonomy (lines 621-653). Line 433: model-format recovery is outside long-build state. |
| Minor 1: env_summary privacy | Fixed | Lines 203-211: versioned policy, whitelisted names, secret omission, value clipping, no raw dumps. |
| Minor 2: Anti-accretion gate location | Fixed | Lines 1013-1034: concrete enforcement surface with machine-readable records in gap ledger, enumerated required fields, prompt metric/hash snapshot test. |
| Minor 3: Source authority fixture | Fixed | Lines 1080-1083: `unverified_source_build_rejected` added. Four additional negative fixtures also added (lines 1085-1093). |

### All merged findings

| Merged finding key | Addressed? | How |
| --- | --- | --- |
| `command-evidence-ref-ordering-and-scope` | Yes | Lines 168-188: numeric id/ref, monotonic ordering, freshness rules. Lines 192-201: synthesis scope. |
| `long-build-contract-authority-and-runtime-classifier` | Yes | Lines 286-310: authority precedence with 5-level ordering. Lines 312-326: runtime proof classifier with positive/negative rules and ambiguity tiebreakers. |
| `flag-day-cutover-not-legacy-projection` | Yes | Lines 767-804: Flag-Day Cutover section. Lines 113-115: explicit premise. |
| `current-blocker-to-failure-class-inventory` | Yes | Lines 655-676: table mapping 16 current blocker families to generic failure classes with clear conditions. |
| `recovery-decision-scope-and-recent-blockers` | Yes | Lines 430-433, 463: scope excludes finish and model-format. Lines 631-633: `source_provided_branch_unchecked` and `vendored_dependency_surgery_too_early` in taxonomy. |
| `anti-accretion-enforcement` | Yes | Lines 1013-1034: snapshot test, required record fields, transfer fixture requirement, review-gate rule. |
| `contract-driven-stages` | Yes | Lines 414-423, 686-691. Stage array example (line 382-386) is dynamic, not fixed. |
| `migration-tests-not-byte-compat` | Yes | Throughout: "behavior/safety parity" replaces byte compatibility. Lines 796-804 enumerate parity dimensions. |
| `schema-version-and-env-privacy` | Yes | Lines 821-828: schema version policy. Lines 139, 203-211: env privacy. |
| `transfer-fixtures-negative-cases` | Yes | 10 fixtures (lines 1065-1093) including 5 negative cases. |

## Focus Area Assessment

### 1. Flag-day/no-backcompat cutover safety

The cutover contract (lines 767-804) is well-bounded:

- Clearly lists what may be removed (5 items, lines 774-783).
- Enumerates what must be preserved (7 safety invariants, lines 787-794).
- Defines behavior/safety parity (6 dimensions, lines 796-804) as the replacement for byte compatibility.
- Explicitly excludes migrating old active sessions (line 1136).
- Excludes supporting old `tool_call` refs after cutover (line 1138).

This is safe because mew is unreleased and the safety invariants are preserved through parity tests, not through state compatibility.

### 2. Deterministic acceptance evidence and done-gate authority

Preserved. Key assurances:

- Line 495-496: "No concept above can independently complete a task."
- Lines 756-765: acceptance evidence invariant rules.
- Line 473: RecoveryDecision "never mark[s] acceptance complete and never weaken[s] the done gate."
- Line 764-765: old `tool_call` refs not required after cutover, done gate remains authority.
- Lines 589-602: acceptance layer integration preserves the invariant unchanged.

### 3. Concept precision for implementation

All five core concepts have sufficient detail for Phase 0:

- **CommandEvidence**: id/ref (integer, not string), ordering (`start_order`/`finish_order`), freshness rules, synthesis scope, env privacy. Sufficient.
- **LongBuildContract**: authority precedence (5 levels), runtime proof classifier with ambiguity rules, minimum field schema. Sufficient.
- **BuildAttempt**: unchanged from round 1, adequate for Phase 0.
- **LongBuildState**: contract-driven stages with omission policy, minimum field schema. Sufficient.
- **RecoveryDecision**: scope boundary, 3-value decision enum, minimum field schema. Sufficient.
- **Anti-accretion**: concrete enforcement with test, record format, and review gate. Sufficient.
- **Transfer fixtures**: 10 named fixtures with expected behavior descriptions. Sufficient.

### 4. Remaining must-fix issues

None found. The design is ready for Phase 0 implementation.

## Observations (non-blocking)

1. **Ordering counter scope**: The freshness rules (line 184-186) reference "no later command or write mutation with order greater than the proof `finish_order`." This implies write operations participate in the same monotonic counter space as command evidence. The implementation will need to decide whether write tools also allocate order counters or whether freshness is checked differently for write mutations. This is a Phase 1 implementation detail, not a design gap.

2. **Compound command segmentation**: The design says one BuildAttempt per command tool call in v1 (line 331-332). The existing `split_unquoted_shell_command_segments` in `acceptance_evidence.py` could support segment-level classification later, but v1 correctly defers this.

3. **Command evidence storage**: Open question (line 1143-1144) remains open. This is correctly deferred to implementation since the answer affects code structure, not design correctness.

## Conclusion

The revised design addresses all accepted round-1 findings thoroughly. The flag-day cutover is clean and preserves safety invariants through behavior/safety parity rather than byte compatibility. The design is ready for Phase 0 implementation.
