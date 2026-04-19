# M2 Comparative Dogfood - 2026-04-19

Milestone: M2 Interactive Parity

Task: make `mew dogfood --scenario m2-comparative` artifacts directly fillable
after a paired run by adding `generated_at`, `comparison_result`, per-run
summaries, and a Markdown `Comparison Result` section.

## Runs

### mew

- Entry: `mew code 241 --quiet --timeout 0 ...`, then
  `mew work 241 --follow ...`
- Task/session: task `#241`, work session `#235`
- Result: blocked without supervisor help
- Verification: two attempted test-only approvals failed and rolled back
- Summary: mew found the right files, read the right windows, and generated the
  intended test patch. The first source edit was stopped by paired-test
  steering, which correctly wanted a test edit first. Approval then verified the
  test-only change before the source change existed, failed, and rolled it
  back. Repeating the step recreated the same loop.

Friction counts:

- retyped_gate_flags: 0
- lost_context_or_rebriefs: 0
- manual_status_probes: 1
- approval_confusions: 2
- verification_confusions: 2
- dead_waits_over_30s: 2
- restart_or_recovery_steps: 2

Resume behavior:

- interrupt_point: pending approval / rollback loop after paired-test steer
- could_resume_without_user_rebrief: mostly yes
- risky_or_missing_context: approval semantics made the correct next move
  unclear, not missing memory

### fresh_cli

- Entry: `codex-ultra` in detached worktree `/tmp/mew-fresh-cli-a3cc4c7`
- Result: completed without supervisor changes
- Verification:
  - `python3 -m py_compile src/mew/dogfood.py`
  - `uv run pytest tests/test_dogfood.py -k m2_comparative -q`
- Summary: fresh CLI made the local source+test change directly and reported
  only minor environment friction (`python` missing, then used `python3` and
  `uv`).

Friction counts:

- retyped_gate_flags: 0
- lost_context_or_rebriefs: 0
- manual_status_probes: 0
- approval_confusions: 0
- verification_confusions: 1
- dead_waits_over_30s: 0
- restart_or_recovery_steps: 0

## Comparison Result

- status: fresh_cli_preferred
- next_blocker: paired source/test approval semantics
- notes: For small local changes, mew's persistent cockpit is not yet worth the
  approval/verification overhead. The specific blocker is not memory or file
  navigation; it is that paired-test steering asks for the test first while
  approval verification requires the test to pass before the source edit exists.
  That can trap the resident in a rollback loop.

## Follow-Up

The next M2 slice should make paired source/test edits pass through the approval
boundary as a unit, or support an explicit expected-failing test approval mode
for resident TDD flows. This should reduce approval confusion and verification
rollback without weakening the safety gate.
