# M6.24 Long-Build Substrate Phase 0

Date: 2026-05-01
Status: reviewed

## Scope

Implemented Phase 0 from
`docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`.

This phase adds schema helpers and test-only synthesis. It intentionally does
not change production prompt rendering, command execution, acceptance refs, or
Terminal-Bench behavior.

## Added

- `src/mew/long_build_substrate.py`
  - `CommandEvidence`
  - `LongBuildContract`
  - `BuildAttempt`
  - `LongBuildState`
  - `RecoveryDecision`
  - test-only synthesis from old `run_command` / `run_tests` tool calls
  - environment summary privacy helper
  - artifact proof parity helper from synthesized `CommandEvidence`
  - ordering/freshness helper for fixture-level mutation rejection
- `tests/test_long_build_substrate.py`
  - terminal-success parity with current `tool_call_terminal_success`
  - strict artifact-proof parity with
    `long_dependency_artifact_proven_by_call`
  - rejection coverage for timeout, masked proof, spoofed proof, path-prefix
    proof, same-command post-proof mutation, later exact-path mutation, parent
    glob mutation, and cwd-relative mutation
  - proof that write tools and write-tool `verify_command` fields are not
    synthesized into `CommandEvidence`
  - schema-shape smoke coverage for all five long-build records
  - preservation of non-stdout output surfaces used by current acceptance
    helpers
  - env summary privacy tests

Out of scope for Phase 0:

- contract extraction
- `LongBuildState` reducer behavior
- `RecoveryDecision` derivation
- prompt or runtime cutover

## Validation

Passed:

```text
uv run pytest -q tests/test_long_build_substrate.py --no-testmon
19 passed

uv run pytest -q tests/test_acceptance.py -k 'long_dependency or acceptance_done_gate' --no-testmon
24 passed, 91 deselected

uv run pytest -q tests/test_long_build_substrate.py tests/test_acceptance.py --no-testmon
134 passed

uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py
All checks passed
```

Review:

- `docs/REVIEW_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE_PHASE_0_CODEX.md`
  records the codex-ultra review history and final `PASS`.

## Next

If review passes, commit Phase 0 and move to Phase 1 native
`CommandEvidence` cutover. Do not run `compile-compcert` speed/proof
measurement after Phase 0 alone.
