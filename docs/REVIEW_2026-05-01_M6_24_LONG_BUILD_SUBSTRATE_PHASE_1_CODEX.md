# Review 2026-05-01 - M6.24 Long-Build Substrate Phase 1

Reviewer: codex-ultra

Session: `019de38b-fc9b-72f1-846a-987ea63d6d58`

Scope:

- `src/mew/long_build_substrate.py`
- `src/mew/work_session.py`
- `src/mew/acceptance.py`
- `src/mew/work_loop.py`
- `tests/test_long_build_substrate.py`
- `tests/test_acceptance.py`
- `tests/test_work_session.py`

## Round 1

Verdict: `REQUIRED_CHANGES`

Required fixes:

1. Command-evidence refs were only accepted by the generic done-gate ref
   validator. External ground-truth command and exact command example semantic
   blockers still resolved only legacy `tool #N` text.
2. Prompt-facing tool-call context and resume command records did not expose
   `command_evidence_ref`. Because command-evidence ids are independent from
   tool-call ids, the model could cite the wrong id after an earlier
   non-command tool.

## Round 2

Verdict: `REQUIRED_CHANGES`

Required fix:

1. Remaining command-output semantic helpers still used legacy `tool #N`
   parsing. Runtime artifact grounding was the concrete failure example.

## Round 3

Verdict: `PASS`

Reviewer summary:

- Structured `command_evidence` refs flow through command-output semantic
  validators.
- Legacy `tool_call` refs remain supported.
- Native command evidence refs are visible in prompt and resume paths.
- Runtime-artifact command-evidence coverage was spot-checked.

Non-blocking note:

- The standalone commands view also needed `command_evidence_ref`; this was
  fixed before commit.

## Final Follow-Up

Verdict: `PASS`

Reviewer summary:

- `build_work_session_command_entries()` now carries `command_evidence_ref`.
- Formatter and test coverage exercise the tool-call id / command-evidence id
  divergence case.
- No blocking Phase 1 issue remains.
