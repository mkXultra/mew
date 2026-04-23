# M6.11 Post-449 Recursive Blocker Review - Codex

Date: 2026-04-24
HEAD: `04b0289`
Task/session: `#465` / `#449`

STATUS: FAIL

COUNTEDNESS: non-counted

DECISION:

Reject session `#449` for M6.11 current-head calibration. It did not exercise the intended no-active-todo replay-capture seam. The only executed tool call recursively invoked:

`./mew work 465 --live --auth auth.pro.json --model-backend codex ... --max-steps 1`

from inside active session `#449`, and the nested CLI exited immediately with `stop=work_already_running` / `mew work ai: work session #449 is already running` before any live sample step, replay writer, or verifier ran. There is no `.mew/replays/work-loop/2026-04-23/session-449` directory, and `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json` on `04b0289` still reports `calibration.cohorts.current_head.total_bundles = 0`.

EXACT BLOCKER:

`work_already_running` caused by same-session recursive resident-loop self-invocation. Reviewer wording: the measured sample was misrouted into orchestration recursion, so the child `mew work` process reattached to the already-running parent session and was rejected before the patch_draft / replay path under test could execute.

The later `objc` after-fork text should be treated as secondary teardown noise after the invalid nested launch, not as the calibration blocker to count.

RECOMMENDED NEXT FIX:

Do a structural fix before spending another measured sample. The highest-value local fix is to forbid resident mew-loop self-invocation through `run_command` inside active work sessions, and mirror that rule in the THINK prompt.

Minimal fix shape:

1. Add a runtime guard that rejects `run_command` when argv resolves to `mew` / `./mew` and subcommand `work`, `chat`, `run`, or `do`, with an explicit recovery message to use `finish`, `wait`, `remember`, `--steer`, `--queue`, or an external operator-run CLI instead.
2. Add the same prohibition to the work prompt so the model does not copy printed `Next CLI controls` into a `run_command` action.
3. If needed, mark printed `Next CLI controls` as operator-only or suppress them from nested captured command output to reduce prompt contamination.

LIKELY CODE AREAS:

- [src/mew/work_session.py](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:1853): `run_command` currently checks only `allow_shell` and empty command, so resident-loop recursion is allowed through.
- [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:2678): prompt forbids resident mew loops for `run_tests`, but not for `run_command`.
- [src/mew/commands.py](/Users/mk/dev/personal-pj/mew/src/mew/commands.py:2157): `format_work_cli_controls()` prints `one live step` / `follow loop` commands that were then copied back into the session.
- [src/mew/commands.py](/Users/mk/dev/personal-pj/mew/src/mew/commands.py:3903): nested `mew work` correctly stops with `work_already_running`; the problem is that this substrate blocker is reachable from inside the session at all.
- [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1754): finish gate correctly prevents verifier-only closure here, which is why this remains non-counted.

LEDGER_ROW_RECOMMENDATION:

```json
{"recorded_at":"2026-04-24T00:00:00+09:00","head":"04b0289","task_id":465,"session_id":449,"attempt":null,"scope_files":["src/mew/patch_draft.py","tests/test_patch_draft.py"],"verifier":"uv run python -m unittest tests.test_patch_draft.PatchDraftTests","counted":false,"non_counted_reason":"session #449 never reached the intended current-head patch_draft replay seam; it recursively invoked `./mew work 465 --live ...` from inside the same active session, hit `stop=work_already_running`, emitted no same-session replay artifact, and left `current_head.total_bundles=0`","blocker_code":"work_already_running","reviewer_decision":"rejected_as_recursive_same_session_work_invocation","replay_bundle_path":null,"review_doc":"docs/REVIEW_2026-04-23_M6_11_POST_449_RECURSIVE_BLOCKER_CODEX.md","notes":"Treat later objc after-fork crash text as secondary teardown noise after the invalid nested launch, not as counted replay/blocker evidence. Rerun the measured sample only after a structural resident-loop recursion guard lands."}
```
