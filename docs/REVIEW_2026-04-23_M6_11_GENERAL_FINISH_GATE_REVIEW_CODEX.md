STATUS: PASS

FINDINGS:

- None.

DECISION: Safe to commit. The generalized predicate in `src/mew/work_loop.py:1638`-`1651` gates the explicit `Do not finish from a passing verifier alone` contract independently of the old `patch_draft` sample detector, while `src/mew/work_loop.py:1746`-`1750` preserves the previous verifier-closeout allowance only for tasks without that phrase. The #457-shaped dogfood regression in `tests/test_work_session.py:9835`-`9935` blocks fixture-only verifier finish, and the existing non-over-gating tests in `tests/test_work_session.py:10063`-`10123` still allow ordinary implementation/current-head tasks that lack the explicit phrase.

NEXT: Commit the scoped changes, including this review file, with `git add src/mew/work_loop.py tests/test_work_session.py proof-artifacts/m6_11_calibration_ledger.jsonl docs/REVIEW_2026-04-23_M6_11_POST_457_CODEX.md docs/REVIEW_2026-04-23_M6_11_GENERAL_FINISH_GATE_REVIEW_CODEX.md && git commit -m "Generalize M6.11 no-verifier finish gate"`.

Validation observed: `uv run pytest tests/test_work_session.py -q -k 'calibration_measured_patch_draft_finish or calibration_measured_dogfood_finish or calibration_finish_with_rejected or does_not_gate_non_patch_draft_current_head_sample or does_not_gate_fix_first_task' --no-testmon` passed with 12 tests.
