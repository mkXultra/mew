# M2 True Restart Comparator Dogfood 2026-04-20

Purpose: test the M2 fresh-restart comparator path after adding explicit
fresh CLI context fields and restart prompt assets.

## Mew Leg

Task: `#268`

Work session: `#256`

Shape:

- `mew code 268 --quiet --timeout 0`
- `mew work 268 --follow ... --approval-mode accept-edits --compact-live`
- mew wrote the paired failing test first
- mew attempted the source edit twice
- both source attempts rolled back because focused pytest still failed
- the supervisor completed the narrow source fix manually
- failed pending source approvals `#1568` and `#1574` were rejected as
  superseded
- task-level user-reported verification `#47` recorded the later passing
  supervisor validation

Mew evidence after the task-level verification fix:

- `mew_run_evidence.verification.status: passed`
- `mew_run_evidence.verification.source: task_verification`
- `mew_run_evidence.verification.verification_run_id: 47`
- `interruption_resume_gate.mew.status: proved`
- `interruption_resume_gate.mew.verification_run_ids: [47]`

## Fresh Restart Leg

Runner: `codex-ultra` through `acm run`

Worktree: `/tmp/mew-fresh-restart-session-arg`

Base: `a1f6732`

Report: `/tmp/mew-fresh-restart-session-arg-report.json`

Shape:

- detached worktree from before the mew-side fix
- new agent session, no prior session resume
- prompt required `fresh_cli_context_mode: true_restart`
- implemented the same source/test change
- wrote the required JSON report

Verification:

- `uv run pytest --no-testmon -q tests/test_dogfood.py -k m2_comparative`
- `uv run ruff check src/mew/dogfood.py tests/test_dogfood.py`
- `git diff --check`

Fresh report summary:

- `fresh_cli_context_mode: true_restart`
- `fresh_cli_session_resumed: false`
- `fresh_cli_handoff_note_used: false`
- `fresh_cli_restart_comparator_status: proved`
- `manual_rebrief_needed: true`
- `interruption_resume_gate: not_proved`
- `resident_preference.choice: mew`

## Combined Result

Combined artifact:

- JSON:
  `/tmp/mew-m2-true-restart-combined-task-verification/.mew/dogfood/m2-comparative-protocol.json`
- Markdown:
  `/tmp/mew-m2-true-restart-combined-task-verification/.mew/dogfood/m2-comparative-protocol.md`

Result:

- `comparison_result.status: mew_preferred`
- `interruption_resume_gate.mew.status: proved`
- `interruption_resume_gate.fresh_cli.context_mode: true_restart`
- `interruption_resume_gate.fresh_cli.restart_comparator_status: proved`
- `interruption_resume_gate.fresh_cli.status: not_proved`
- top-level `interruption_resume_gate.status: not_proved`

## Interpretation

This closes a measurement gap, not M2 itself.

The fresh restart comparator now works and proved it can start from a clean
external agent session, implement the task, verify it, and produce a mergeable
report. The same run also showed why mew's resident path matters: once the
task-level verification was included, mew could carry the original session
selector and later supervisor verification into the M2 evidence bundle.

The M2 interruption-resume gate still remains open because the fresh restart
leg was not itself an interrupted fresh CLI resume. The next strongest evidence
would be a task where:

- mew is interrupted and resumes through its work-session bundle
- fresh CLI starts from a true fresh restart
- both sides complete verification
- the resident preference is judged from that paired evidence
