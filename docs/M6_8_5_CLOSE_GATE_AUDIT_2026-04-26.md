# M6.8.5 Close Gate Audit - 2026-04-26

Milestone: **M6.8.5 Selector Intelligence and Curriculum Integration**

Verdict: **closed**

## Scope

M6.8.5 absorbed the M6.9 Phase 4 work that was intentionally gated on the
M6.8 supervised selector contract. The selector remains reviewer-gated and
read-only: it can surface evidence that helps a reviewer approve the next task,
but it still cannot dispatch work, mutate governance, close milestones, or
change approval policy.

## Gate Evidence

| Done-when criterion | Evidence |
|---|---|
| Failure-clustered selector signal proposes a next task from recorded evidence | Task `#639` / session `#627` attached `failure_cluster_reason` from the M6.12 calibration ledger to non-blocked proposals. Dogfood proposal `#16` carried `preflight_gap:9` while preserving `approval_required=true` and no dispatch. Commit `f664032`. |
| Preference evidence is reviewer-visible | Task `#641` / session `#629` attached bounded `preference_signal_refs` from selector reviewer history. Dogfood proposal `#18` carried failure-cluster and preference refs into the next handoff. Commit `73e9329`. |
| Calibration/evaluator memory refs are available to the selector | Task `#642` / session `#630` attached bounded calibration/evaluator rows as `memory_signal_refs` from `proof-artifacts/m6_11_calibration_ledger.jsonl`. Dogfood proposal `#19` carried memory, failure, and preference refs. Commit `629e611`. |
| Selector traces explain why a task was chosen without replaying raw state | Tasks `#639`, `#641`, `#642`, `#643`, `#645`, and `#646` recorded the signal refs directly on proposals and in `mew task selector-status --json`. Latest selector status reports `approved_handoffs=10`, `rejected_attempts=2`, `blocked_proposals=7`, and `proof_summary.contiguous_chain_length=5`. |
| Stable task template compiles into a deterministic runner candidate | Task `#643` / session `#631` attached repeated `selector_habit_template` evidence; task `#645` / session `#632` emitted `compiled_habit_runner_candidate` only when approved handoff evidence matched the deterministic `./mew work <task> --start-session` command. Mismatch falls back to the model path. Commits `e3b6b0d` and `dd71a14`. |
| Preference-store pair is retrieved during draft preparation | Task `#646` / session `#633` surfaces approved selector `preference_signal_refs` in work-session resume and THINK prompt context with bounded provenance. Missing, unapproved, or wrong-task records produce an empty field, and `memory_signal_refs` are not used as fallback. Commit `d22d09c`. |
| M6.8 approval and scope fence still hold | All signal use is proposal/resume context only. Handoffs still require reviewer approval, `auto_run=false`, and selector-owned output does not edit roadmap, milestone-close, or governance files. |

## Mew-First Accounting

- `#639`: `success_after_substrate_fix`. The accepted source/test patch was
  mew-authored after M6.14 classified and repaired a synthetic-schema failure.
- `#641`: `success_mew_first_with_reviewer_revisions`. Reviewer rejected a
  non-ASCII truncation draft and steered the target path; mew authored the
  accepted patch.
- `#642`: `success_mew_first_with_reviewer_steer`. Reviewer steered the cached
  anchors after read churn; mew authored the accepted patch.
- `#643`: `success_after_substrate_fix`. M6.14 repaired write-ready recovery
  cues in commit `161180b`; mew then authored the accepted patch.
- `#645`: `success_mew_first`. No supervisor product rescue.
- `#646`: `success_mew_first_with_reviewer_revision`. Reviewer rejected a
  fallback from `preference_signal_refs` to `memory_signal_refs`; mew removed
  the fallback and added THINK-prompt proof.

## Validation

Representative validation across the closed M6.8.5 slices:

- `uv run pytest -q tests/test_commands.py --no-testmon`
- `uv run pytest -q tests/test_tasks.py tests/test_commands.py --no-testmon`
- `uv run pytest -q tests/test_work_session.py -k 'selector_preference_refs_in_prompt' --no-testmon`
- `uv run pytest -q tests/test_work_session.py -k 'selector_preference_refs_in_prompt or hard_timeout_without_retries' --no-testmon`
- `uv run pytest -q tests/test_work_session.py --no-testmon`
- `uv run ruff check src/mew/commands.py tests/test_commands.py`
- `uv run ruff check src/mew/work_session.py tests/test_work_session.py`
- `git diff --check`

The first full `tests/test_work_session.py` run during `#646` had one transient
hard-timeout assertion failure. The exact failing test and the full suite both
passed immediately on rerun.

## Caveats

- M6.8.5 implements selector intelligence as reviewer-visible signals, not
  autonomous task dispatch.
- `compiled_habit_runner_candidate` is a deterministic runner candidate record,
  not an auto-execution path.
- Preference evidence is bounded and provenance-bearing, but still basic; it
  does not perform semantic ranking beyond current selector history.
- M6.13 deliberation lane remains separate. It should be evaluated next because
  the prior deferral condition, "after M6.8.5 or direct hard-blocker evidence",
  has now fired.

## Close Decision

M6.8.5 is closed because mew can now carry failure clusters, reviewer
preference evidence, calibration memory, habit templates, compiled runner
candidates, and draft-prep preference context through a supervised selector
chain while preserving the M6.8 approval and scope-fence contract.
