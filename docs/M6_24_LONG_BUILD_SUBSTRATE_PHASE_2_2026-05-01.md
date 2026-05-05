# M6.24 Long-Build Substrate Phase 2

Date: 2026-05-01
Status: reviewed

## Scope

Implemented Phase 2 from
`docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`.

This phase cuts the long-build resume state from the old
`long_dependency_build_state` shape to `long_build_state`. It intentionally
does not add `RecoveryDecision` action derivation, budget enforcement, or
Terminal-Bench measurement.

## Added

- `src/mew/long_build_substrate.py`
  - builds `LongBuildContract` from task text and required artifacts;
  - reduces `CommandEvidence` plus contract policy into `LongBuildState`;
  - records source authority, target artifact, default-smoke, runtime, blocker,
    and failure-class state in one typed structure;
  - preserves safety parity for terminal-success, masked proof, post-proof
    mutation, opaque wrapper, and command-token artifact proof cases.
- `src/mew/work_session.py`
  - builds `work_session.resume.long_build_state`;
  - prefers native `command_evidence` and uses synthesized evidence only for
    legacy fixture-shaped tests;
  - formats the new state in resume text.
- `src/mew/work_loop.py`
  - points implementation-lane prompt context at `long_build_state`.

Out of scope:

- `RecoveryDecision` derivation and rendering;
- recovery-budget enforcement from the new state;
- provider-specific cache transport;
- `compile-compcert` speed/proof measurement.

## Validation

Final validation:

```text
uv run pytest --no-testmon -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py
1028 passed, 1 warning, 67 subtests passed

uv run ruff check src/mew/long_build_substrate.py src/mew/work_session.py src/mew/work_loop.py tests/test_long_build_substrate.py tests/test_work_session.py
All checks passed

git diff --check
passed
```

## Review

- codex-ultra review session
  `019de3ab-47b6-71c3-849d-db3f089e1ecd` returned `PASS`.
- The review required multiple safety-hardening rounds around:
  - exact artifact invocation and basename cwd rules;
  - source-authority completion requirements;
  - artifact and default-smoke freshness after later mutation;
  - marker-only and echo/printf spoofing;
  - realistic package-manager metadata outputs.
- `docs/REVIEW_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE_PHASE_2_CODEX.md`
  records the review history.

## Next

Move to Phase 3: derive `RecoveryDecision` for the narrow failure classes
listed in the design and render it into `long_build_state`.

Do not run `compile-compcert` speed/proof measurement after Phase 2 alone.
