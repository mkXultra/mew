# M6.11 Drafting Recovery — Codex Review

## Verdict

**approve**

## Findings

- None. The prior medium findings are resolved in the live diff:
  - `src/mew/dogfood.py:767-772` now evaluates the direct `build_work_session_resume(...)` side under the temporary dogfood workspace, and I re-checked that the scenario output is identical when invoked from repo root versus an unrelated cwd.
  - `tests/fixtures/work_loop/drafting_recovery/blocker_code_parity/scenario.json:21,129` now pins the equal-timestamp richer-overlay path, and `src/mew/dogfood.py:874-883` asserts `session_state_newer == false` together with `resume_source == "session_overlay"`.
  - `src/mew/dogfood.py:843-911` now compares broader parity surfaces (`active_work_todo`, blocker detail, next action, suggested recovery shape/reason) instead of only scalar ids/codes.

## Residual Risks

- This fixture covers one blocked-on-patch blocker shape (`ambiguous_old_text_match`). Other blocker-code mappings still rely on lower-level coverage rather than dogfood-level parity coverage.
- The scenario is intentionally stale-snapshot-based (`follow_status=status=stale`), so it does not say anything about active producer or timeout behavior.
- `m6_11-draft-timeout`, `m6_11-refusal-separation`, and `m6_11-phase4-regression` remain `not_implemented`, so `dogfood all` should continue to fail honestly after this slice lands.

## Suggested Validation Additions

- Keep `./.venv/bin/python -m pytest tests/test_dogfood.py -k m6_11` and `./.venv/bin/python -m mew dogfood --scenario m6_11-drafting-recovery` in the slice validation set.
- Add a targeted test that runs `run_dogfood_scenario(...)` from a non-repo cwd, so the workspace-root determinism fix is pinned automatically instead of only by manual re-check.
- When a second drafting-recovery slice is warranted, add another fixture with a different blocker code so dogfood covers more than one recovery-action taxonomy branch.
