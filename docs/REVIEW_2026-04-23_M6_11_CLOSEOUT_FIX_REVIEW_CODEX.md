# M6.11 Closeout Recognition Fix Review

Findings:

1. **P1 - `recent_decisions` fallback can create a stale verifier false positive without closeout metrics.**  
   In `src/mew/work_loop.py:1493-1527`, the fallback synthesizes `write_ready_fast_path=False` and `write_ready_fast_path_reason="recent_decisions_closeout"` from any compacted completed `run_tests` decision with matching `target_paths` and `tool_call_id`. That bypasses the guard at `src/mew/work_loop.py:1566-1569`, even when the original model turn had no persisted closeout metrics. This contradicts the existing no-metrics protection covered by `tests/test_work_session.py:7244`. A compact context with `model_turns=[]`, a matching `resume.recent_decisions` entry, and a passed latest `run_tests` tool call currently returns true from `_write_ready_fast_path_verifier_closeout_passed`. Prefer using only `latest_verifier_closeout` or preserving/checking the real metrics on compacted decisions.

2. **P2 - Tests do not force the observed #451 compact-context shape.**  
   The new positive tests at `tests/test_work_session.py:7288` and `tests/test_work_session.py:9156` still keep the verifier model turn in `work_session.model_turns`, so `_work_write_ready_fast_path_latest_completed_verifier_model_turn` returns before the new `resume.latest_verifier_closeout` path at `src/mew/work_loop.py:1478`. These tests would still pass if `build_work_session_resume` stopped emitting `latest_verifier_closeout` or if work-loop ignored it. Add a focused case where compacted context drops the verifier model turn from `model_turns`/`recent_decisions` but retains `resume.latest_verifier_closeout` plus the passed verifier tool call.

3. **P2 - `latest_verifier_closeout` target-path preservation is narrower than live turn recognition.**  
   Live model-turn recognition accepts `turn.target_paths`, `decision_plan.target_paths`, and `decision_plan.working_memory.target_paths` (`src/mew/work_loop.py:1454-1458`), but `build_work_session_resume` records only `decision_plan.working_memory.target_paths` in `latest_verifier_closeout` (`src/mew/work_session.py:5197-5208`). If compacting drops the verifier model turn, a valid verifier closeout using one of the other accepted target-path locations will still fail the same-surface check.

No implementation files were edited for this review.
