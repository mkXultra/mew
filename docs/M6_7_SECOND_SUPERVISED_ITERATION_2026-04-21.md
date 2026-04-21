# M6.7 Second Supervised Iteration 2026-04-21

Status: passed.

This document records the second bounded reviewer-gated M6.7 self-hosting
iteration.

## Iteration Shape

- task: `#365` `M6.7 second supervised loop: proof-or-revert finish block`
- session: `#353`
- reviewer: Codex
- implementer: mew native work session
- scope fence: `src/mew/commands.py`, `src/mew/work_session.py`,
  `tests/test_work_session.py`
- explicit non-goals: `ROADMAP.md`, `ROADMAP_STATUS.md`, `docs/`, and
  unrelated files

## Drift Canary

Ran before the iteration:

```bash
uv run pytest -q \
  tests/test_work_session.py::WorkSessionTests::test_resume_surfaces_same_surface_audit_for_mew_source_edit \
  tests/test_work_session.py::WorkSessionTests::test_resume_surfaces_low_confidence_before_source_approval \
  --no-testmon
```

Result: `2 passed in 1.06s`

## Reviewer-Gated Run

The live run started with bounded guidance and write roots limited to
`src/mew` and `tests`. mew eventually converged on the finish-close path in
`src/mew/commands.py`, produced a paired dry-run diff, stopped for review,
and then completed the bounded proof flow:

1. anchored the `apply_work_control_action(..., action_type == "finish")`
   branch and the nearest finish regressions
2. produced paired dry-run diffs in `src/mew/commands.py` and
   `tests/test_work_session.py`
3. stopped on pending approval
4. after reviewer approval, ran the focused verifier
   `uv run pytest -q tests/test_work_session.py -k 'finish_block' --no-testmon`
5. ran the broader paired-source verifier
   `uv run python -m unittest tests.test_commands`
6. performed one narrow same-surface audit in `src/mew/commands.py`
7. finished with an explicit keep decision and no reviewer rescue edits

Reviewer actions:

- one steering correction to stop broader finish-path discovery and force the
  exact `commands.py` finish branch plus the nearest regression anchors
- approved dry-run test edit `#2820`
- approved dry-run source edit `#2821`
- one narrow same-surface audit steer
- no direct reviewer code edits

## Change Landed

Files changed:

- `src/mew/commands.py`
- `tests/test_work_session.py`

Behavior added:

- `apply_work_control_action()` now blocks `finish` from closing the active
  work session when the resume still shows:
  - pending approvals
  - non-finish-ready source-edit verification confidence
  - a required same-surface audit
- the finish branch appends a blocked note instead of closing the session
- regression coverage verifies that the session stays open and the task is not
  marked done while those blockers exist

## Verification

Focused verifier after approval:

```bash
uv run pytest -q tests/test_work_session.py -k 'finish_block' --no-testmon
```

Result: `1 passed, 416 deselected, 3 subtests passed in 0.48s`

Broader paired-source verifier before finish:

```bash
uv run python -m unittest tests.test_commands
```

Result: `Ran 179 tests ... OK`

Additional reviewer checks after the run:

```bash
uv run ruff check src/mew/commands.py tests/test_work_session.py
uv run python -m py_compile src/mew/commands.py tests/test_work_session.py
uv run python -m unittest tests.test_work_session tests.test_commands
git diff --check
```

Result: pass

## Same-Surface Audit Conclusion

No additional sibling `commands.py` update was needed.

- The active finish branch is the correct place to block closure.
- The nearby `finished_note` propagation already forwards the blocked finish
  note unchanged.
- The closed-session control surface is downstream of `close_work_session()`
  and is therefore out of scope for this slice once the new guard stops the
  session from reaching that path while proof blockers remain.

## Why This Counts

This iteration provides the missing direct M6.7 hardening slice for
proof-or-revert:

- the task could not finish as credited work while approvals, verification, or
  same-surface audit were incomplete
- the iteration still used a reviewer-gated dry-run approval surface
- verification was broadened to the paired `commands.py` module before finish
- no reviewer rescue edits were needed

## Next Gap

The next M6.7 task should harden scope fence enforcement beyond visible
declared write roots and reviewer-bounded docs/governance non-goals.
