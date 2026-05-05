# M6.24 Long-Build Substrate Phase 1

Date: 2026-05-01
Status: reviewed

## Scope

Implemented Phase 1 from
`docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`.

This phase cuts production command execution over to native
`CommandEvidence` for terminal command tools. It intentionally does not add
contract extraction, `LongBuildState` reduction, `RecoveryDecision`, or
Terminal-Bench measurement.

## Added

- `src/mew/work_session.py`
  - records native `CommandEvidence` for `run_command` and `run_tests` at tool
    start;
  - updates the same evidence record at tool completion or interruption;
  - stores `command_evidence_ref` on the source tool call;
  - exposes `command_evidence_ref` in resume command records and formatted
    resume/command output, including cases where tool-call ids and command
    evidence ids diverge.
- `src/mew/long_build_substrate.py`
  - adds Phase 1 timeout and wall-budget fields to `CommandEvidence`;
  - converts live tool-call records into native command evidence through
    `command_evidence_from_tool_call()`;
  - maps wall-time ceiling data to requested/effective timeout and budget
    fields when available.
- `src/mew/acceptance.py`
  - resolves `{"kind": "command_evidence", "id": N}` refs for done-gate
    terminal evidence;
  - uses command evidence as final-artifact proof for long dependency checks;
  - resolves command evidence into pseudo command calls for external
    ground-truth and exact command example semantic blockers.
- `src/mew/work_loop.py`
  - updates action schema and guidance to prefer command evidence refs for
    `run_command` / `run_tests`;
  - includes `command_evidence_ref` in prompt-facing tool-call context.

Out of scope:

- `LongBuildContract` extraction;
- `LongBuildState` reducer cutover;
- `RecoveryDecision` derivation;
- provider-specific cache transport;
- `compile-compcert` speed/proof measurement.

## Validation

Passed before review:

```text
uv run pytest -q tests/test_long_build_substrate.py --no-testmon
20 passed

uv run pytest -q tests/test_acceptance.py -k 'command_evidence or external_ground_truth_command_evidence_ref or exact_command_example_command_evidence_ref or acceptance_done_gate' --no-testmon
11 passed, 109 deselected

uv run pytest -q tests/test_work_session.py -k 'command_evidence_ref_is_visible or native_command_evidence or verify_command_is_not_native' --no-testmon
3 passed, 854 deselected

uv run ruff check src/mew/acceptance.py src/mew/work_loop.py src/mew/work_session.py tests/test_acceptance.py tests/test_work_session.py
All checks passed

uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py
All checks passed
```

Final validation:

```text
uv run pytest -q tests/test_long_build_substrate.py tests/test_acceptance.py --no-testmon
141 passed

uv run pytest -q tests/test_work_session.py --no-testmon
857 passed, 1 warning, 67 subtests passed

uv run ruff check src/mew/long_build_substrate.py src/mew/work_session.py src/mew/acceptance.py src/mew/work_loop.py tests/test_long_build_substrate.py tests/test_acceptance.py tests/test_work_session.py
All checks passed

git diff --check
passed
```

## Review

- Initial codex-ultra review session
  `019de38b-fc9b-72f1-846a-987ea63d6d58` returned `REQUIRED_CHANGES`.
- Required fixes:
  - structured command evidence refs had to feed external ground-truth and
    exact command semantic blockers;
  - command evidence ids had to be visible in prompt-facing context and resume
    command records because command evidence ids are independent from tool-call
    ids.
- Round 2 codex-ultra review required routing all remaining command-output
  semantic helpers through the structured ref resolver. Runtime artifact
  grounding was the concrete example.
- Final codex-ultra review returned `PASS`.
- `docs/REVIEW_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE_PHASE_1_CODEX.md`
  records the review history.

## Next

Commit this slice and move to Phase 2 contract extraction and state cutover.
Do not run `compile-compcert` speed/proof measurement after Phase 1 alone.
