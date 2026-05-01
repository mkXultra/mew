# Review 2026-05-01 - M6.24 Long-Build Substrate Codex

Verdict: APPROVE_WITH_CHANGES

The design is pointed at the right substrate: typed command evidence, a small
long-build reducer, compatibility projection, and deterministic acceptance as
the final authority. It is mew-sized if Phase 5 stays deferred and Phases 0-2
land as schema/reducer/projection work before command-runtime changes.

## Findings

### Major - Native command evidence needs ordering/freshness semantics before it can enter acceptance

Target: `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`, `CommandEvidence`, `Acceptance Evidence Invariant`, and Phase 3.

`CommandEvidence` preserves command/cwd/status/output facts, but it does not yet define a monotonic session order, event index, or freshness relation to later artifact-scope mutations. The design also says final proof requires artifact freshness and "no later artifact-scope mutation", and Phase 3 lets acceptance prefer native `command_evidence` refs. Without explicit ordering, a native evidence ref stored outside the current `tool_calls` list can accidentally lose the strict proof/freshness behavior that current `tool_call` refs get from command/cwd/output and session context.

Fix: add a required ordering field for native and synthesized command evidence, such as `session_sequence`, `tool_call_id`, and `created_from_tool_call_index`, plus an acceptance rule that resolves `command_evidence` back to the same proof and mutation/freshness checks as `tool_call`. Phase 3 validation should include native-vs-synthesized parity tests for timed out proof, masked proof, spoofed proof, path-prefix proof, and artifact-scope mutation after the cited proof point.

### Major - LongBuildContract needs an authority/precedence rule for model-provided inputs

Target: `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`, `LongBuildContract`, concept relationship, and Phase 1.

The design says `LongBuildContract` is extracted from task text, action acceptance checks, and possibly model-provided working memory. Current acceptance derives long-dependency artifacts from task text and treats action acceptance checks as model-produced evidence, not as authority to shrink the task. If working memory or acceptance checks can alter `required_artifacts`, runtime proof requirements, or source policy without a precedence rule, the new contract could move a deterministic done-gate boundary into model-controlled state.

Fix: specify that v1 contract authority is task text plus deterministic existing classifiers. Model-provided working memory and action acceptance checks may add provenance, candidate observations, or evidence refs, but must not remove, rename, or weaken task-derived required artifacts, runtime/default-link proof, or final-proof policy. Conflicts should keep the stricter task-derived contract and emit a blocker. Add tests where model memory/checks omit or replace the required artifact and prove the done gate still blocks.

### Minor - Anti-accretion gating is process-strong but not yet mechanically enforceable

Target: `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`, `Anti-Accretion Gate` and Phase 2 validation.

The gate asks the right questions and explicitly rejects benchmark-specific prompt growth, but the implementation path does not require a machine-checkable artifact. Since `prompt_sections.py` already exposes section metrics, the design should require a concrete comparison for static `LongDependencyProfile`, `RuntimeLinkProof`, and `RecoveryBudget` growth. Otherwise the gate can become another review checklist that future fixes bypass under pressure.

Fix: require each long-build prompt/blocker/budget change to record a small anti-accretion gate note or ledger entry and add/update a test or fixture that compares static prompt-section chars/hashes. Static profile growth should fail review unless the gate record explains why dynamic state rendering is insufficient and names the non-CompCert transfer fixture covering it.

## Open Questions

- Native `CommandEvidence` storage can remain open for Phase 0, but Phase 3 should choose inline-on-`tool_calls`, session-level list, or both before exposing `command_evidence` refs.
- The first `BuildAttempt` implementation should probably stay one mew command tool call per attempt. Segment-level attempts can wait until a real parity or recovery problem requires them.
- Source-authority observations need provenance. Parser-derived observations can affect state; model-declared observations should be advisory unless grounded by command/read evidence.

## Implementation Risk Notes

- Preserve the legacy `long_dependency_build_state` projection shape during migration, including `kind`, `progress`, `missing_artifacts`, `strategy_blockers`, and `suggested_next`.
- Keep Phase 0 and Phase 1 behavior-neutral. Prompt/resume behavior changes before projection parity will create noisy M6.24 regressions.
- The transfer plan is good: keep the synthetic fixtures non-CompCert and require them before another proof escalation.
- Keep managed long commands deferred. The current design gets most of the reference-CLI benefit from typed evidence and state without importing a full process manager.
