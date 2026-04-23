STATUS: PASS

FINDINGS:
- None.

REVIEWED:
- `src/mew/work_loop.py`
- `tests/test_work_session.py`

NOTES:
- `work_tool_call_for_model` now exposes `approval_status`, so reviewer/model context can distinguish valid applied/preview evidence from rejected or failed approvals.
- `_calibration_measured_patch_draft_has_paired_patch_evidence` now rejects paired patch evidence with `approval_status` of `rejected`, `failed`, or `indeterminate`.
- Calibration measured `patch_draft` finish remains allowed for valid same-session replay metadata and for paired source+test write evidence.
- Tasks containing `Do not finish from a passing verifier alone` no longer accept verifier-only closeout as finish evidence.

VALIDATION:
- Did not run the full test suite per request.
- Reviewed the main-agent validation results supplied in the prompt:
  - `uv run pytest tests/test_work_session.py -q -k 'calibration_measured_patch_draft_finish or calibration_finish_with_rejected' --no-testmon`: 9 passed
  - `uv run pytest tests/test_work_session.py -q --no-testmon`: 539 passed, 24 subtests
  - `uv run ruff check src/mew/work_loop.py tests/test_work_session.py`: passed
  - `python3 -m py_compile src/mew/work_loop.py`: passed
  - `git diff --check`: passed
