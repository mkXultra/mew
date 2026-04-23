# M6.11 Run Command Guard Patch Review - Codex Final

Date: 2026-04-24
HEAD: `04b0289`
Scope:
- `src/mew/toolbox.py`
- `src/mew/work_session.py`
- `src/mew/work_loop.py`
- `tests/test_work_session.py`
- `proof-artifacts/m6_11_calibration_ledger.jsonl`
- `docs/REVIEW_2026-04-23_M6_11_POST_449_RECURSIVE_BLOCKER_CODEX.md`

STATUS: PASS

Findings:

1. No blocking findings in the scoped diff. The current patch does structurally close the `#449` same-session recursive self-invocation seam for `run_command`.

2. The runtime barrier is now in the correct place: [src/mew/work_session.py](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:1795) adds `reject_resident_mew_loop_command()`, and [src/mew/work_session.py](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:1868) calls it before `run_command_for_work()`. That means `./mew work ... --live` is rejected before spawning a nested resident loop, which is the structural failure mode that produced `stop=work_already_running` in session `#449`.

3. The command detection is centralized and broad enough for the wrapper forms requested here. [src/mew/toolbox.py](/Users/mk/dev/personal-pj/mew/src/mew/toolbox.py:37) parses `python -m mew`; [src/mew/toolbox.py](/Users/mk/dev/personal-pj/mew/src/mew/toolbox.py:56) unwraps `env`, `/usr/bin/env`, `env --`, `env -S` / `--split-string`, and `uv run`; [src/mew/toolbox.py](/Users/mk/dev/personal-pj/mew/src/mew/toolbox.py:136) then classifies resident `mew` subcommands. Direct spot checks against the current code returned `True` for:
- `env -- ./mew work 1 --live`
- `env -S "./mew work 1 --live"`
- `/usr/bin/env mew work 1 --live`
- `uv run mew work 1 --live`
- `uv run -- mew work 1 --live`
- `uv run python -m mew run`
- `python -m mew run`
- `python3 -I -m mew work 1 --live`

4. The benign-command false-positive check passes for the named cases. The same direct classification returned `False` for:
- `echo mew work 1 --live`
- `env -- echo mew work 1 --live`
- `python helper.py mew work 1 --live`
- `uv run pytest -q`
- `/usr/bin/env python -V`

5. The recovery path is correctly adjusted for this pre-exec rejection. [src/mew/work_session.py](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:4788) classifies a failed `run_command` with no result and an error as `no_action`, and [src/mew/work_session.py](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:4346) now only schedules command recovery review when the effect classification is `action_committed`. That prevents a blocked recursive launch from being mis-treated as a command that partially ran.

6. The prompt/test coverage matches the runtime change. [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:2653) now explicitly forbids using `run_command` for resident loops or copied "Next CLI controls". The new tests in [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:5381), [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:5419), [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:15608), and [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:21218) cover the runtime rejection, wrapper recognition, recovery-plan suppression, and shared wrapper handling on the `run_tests` normalization side.

Verification performed:
- `PYTHONPATH=src python3 -m unittest tests.test_work_session.WorkSessionTests.test_work_think_prompt_guides_independent_reads_to_batch tests.test_work_session.WorkSessionTests.test_reject_resident_mew_loop_command_recognizes_wrappers tests.test_work_session.WorkSessionTests.test_work_session_rejects_run_command_resident_mew_loop tests.test_work_session.WorkSessionTests.test_work_recovery_plan_skips_preexec_run_command_guard_failure`
- `PYTHONPATH=src python3 -m unittest tests.test_work_session.WorkSessionTests.test_work_model_rejects_resident_loop_as_verification_command`
- Direct `is_resident_mew_loop_command()` spot checks for the wrapper and benign-command cases listed above

Residual note:

The detector is intentionally wrapper-aware rather than shell-complete. Within the requested scope, it covers the important recursion substrates (`env`, `uv run`, and `python -m mew`) and does not show the benign false positives requested here. If new wrapper families are introduced later, they will need to be added explicitly in the same classifier.
