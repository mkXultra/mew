# Review: M6.24 Long-Build Substrate Phase 4

Reviewer: codex-ultra

Session: `019de42b-0c04-7010-b73e-19f41071fbc1`

## Round 1

Status: `REQUIRED_CHANGES`

Findings:

- `may_spend_reserve` was checked before the planned command stage, so any long
  command after a runtime link/install recovery decision could spend the final
  reserve.
- `block_for_budget` indirectly preserved the reserve only for known
  reserve-preserving stages; other long commands under a budget violation could
  avoid the long-build reserve.

Fix:

- Compute the planned stage first.
- Allow reserve spending only when `RecoveryDecision.decision == continue`,
  `budget.may_spend_reserve == true`, and the planned stage matches
  `allowed_next_action`.
- Preserve reserve for unrelated long commands while a recovery decision is
  active.

## Round 2

Status: `REQUIRED_CHANGES`

Findings:

- `build_system_target_surface_probe` did not include `default_smoke` and
  `artifact_proof`, so a valid combined runtime-subdir recovery plus final
  smoke command could be classified as final proof and incorrectly preserve the
  reserve.

Fix:

- Add `default_smoke` and `artifact_proof` aliases.
- Add a regression proving `build_system_target_surface_invalid` with a final
  default smoke can spend the reserve.

## Final

Status: `PASS`

Findings:

- None.

Additional validation requested:

- None beyond the scoped tests, ruff, and diff check already run.
- Do not run `compile-compcert` measurement yet.
