# Review 2026-05-01 - M6.24 Long-Build Substrate Codex Round 2

Verdict: APPROVE

No required design fixes remain before Phase 0 implementation.

## Findings

No required fixes.

The accepted round-1 findings are addressed:

- `CommandEvidence` now has integer refs, `start_order` / `finish_order`, freshness rules, synthesis limits, and explicit exclusion of write-tool `verify_command` fields from command evidence.
- `LongBuildContract` now has deterministic authority precedence. Model memory and action checks can add observations, but cannot weaken task-derived artifacts, source policy, runtime proof, or final proof.
- The user decision to drop backward compatibility is reflected as a flag-day cutover, with behavior/safety parity replacing byte-identical `long_dependency_build_state` projection.
- The current blocker inventory maps old emitted blocker families to generic failure classes and clear conditions.
- `RecoveryDecision` is now recovery-only: no finish authority and no generic model-format recovery.
- Stages are contract-driven, with irrelevant stages omitted or explicitly `not_required`.
- Anti-accretion enforcement now has a concrete metric/hash snapshot test plus a machine-readable gate record requirement.
- Transfer validation includes positive and negative non-CompCert fixtures, including source authority, runtime-not-required, write-verify exclusion, stale proof, and masked/spoofed proof rejection.

## Cutover Assessment

The flag-day cutover is safe enough for an unreleased internal substrate because it explicitly permits old active sessions to require a fresh proof or new work session, while preserving deterministic acceptance evidence, terminal-success final proof, proof rejection cases, mutation freshness, budget protection, and same-or-better recovery behavior on old fixtures.

The important boundary is clear: old shapes and wording may go away, but done-gate behavior and safety invariants cannot. That is the right tradeoff for this milestone.

## Implementation Risk Notes

- Use one shared session ordering source for command evidence and write/artifact mutations when implementing the freshness guard.
- Decide native `CommandEvidence` storage before Phase 1, not Phase 0.
- Keep Phase 0 limited to schema helpers and the safety-parity harness; no prompt, command runtime, or done-gate behavior change is needed yet.
- Defer long-build relevance thresholds, command-number display details, and managed long-command design to the later phases identified in the design.
