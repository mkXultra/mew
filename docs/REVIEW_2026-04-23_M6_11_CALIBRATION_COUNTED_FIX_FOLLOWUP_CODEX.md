Findings:

1. `src/mew/proof_summary.py:251` still contains dead code. `_read_validator_result_code()` is now unused after the switch to `_read_validator_result()`, so the "dead helper removed" part of this follow-up is not fully true yet.

No other issues found in the reviewed delta. The new ordering in `summarize_m6_11_replay_calibration()` excludes non-counted compiler bundles before malformed/error accounting, which matches the intended behavior. I could not run the targeted pytest cases in this shell because `pytest` is not installed (`python3 -m pytest` fails with `No module named pytest`).
