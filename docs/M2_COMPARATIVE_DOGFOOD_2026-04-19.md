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

## Mitigation

Implemented after this run: single approval now exposes `--defer-verify` through
CLI, `/work-session approve`, reply-file `approve` actions, pending approval
resume hints, and work cells. This lets an observer apply a test-first or other
paired-change write without running the session verifier until the companion
change exists. `approve_all` keeps its existing batch behavior of deferring
intermediate writes and verifying after the final approval.

Validation:

- `./mew dogfood --scenario work-session --json`
- `./mew dogfood --scenario m2-comparative --workspace /tmp/mew-m2-comparative-smoke --json`
- `uv run pytest -q tests/test_dogfood.py -k work_session`
- `uv run pytest -q tests/test_work_session.py -k "defer_default_verification or approve_can_defer_verification or reply_schema_uses_active_session or approve_all_verifies_after_entire_batch or approve_all_applies_paired_test_before_promoted_source_verifier or resume_cli_controls_lead_with_pending_approvals or work_session_cells or source_edit_approval_surfaces_missing_test_pairing or follow_snapshot_surfaces_top_level_pending_approvals"`
- `uv run pytest -q tests/test_work_session.py tests/test_commands.py -k "approve or approval or reply_schema or follow_snapshot or cockpit_controls"`
- `uv run python -m py_compile src/mew/cli.py src/mew/commands.py src/mew/work_session.py src/mew/work_cells.py src/mew/dogfood.py tests/test_work_session.py tests/test_dogfood.py`
- `git diff --check`

## Mitigation Dogfood

Task: add an observer tip to the M2 comparative dogfood protocol so future
paired source/test runs explicitly know to use deferred verification for a
single half of a paired change.

### mew

- Entry: `mew code 242 --quiet --timeout 0 ...`, then
  `mew work 242 --follow ...`
- Task/session: task `#242`, work session `#236`
- Result: completed with observer approval
- Verification:
  - `uv run pytest -q tests/test_dogfood.py -k m2_comparative`
  - `uv run python -m unittest tests.test_dogfood`
  - `./mew dogfood --scenario m2-comparative --workspace /tmp/mew-m2-comparative-observer-tip --json`
  - `uv run python -m py_compile src/mew/dogfood.py tests/test_dogfood.py`
  - `git diff --check`
- Summary: mew started with the right files, hit paired-test steering on the
  first source-first attempt, then created the test change first. The observer
  applied the test edit with `--defer-verify`, avoiding the previous rollback
  loop. mew then proposed an incomplete source edit, accepted rejection
  feedback, and completed the formatter change. The final source approval ran
  the verifier successfully, and mew self-selected the broader
  `uv run python -m unittest tests.test_dogfood` check before finishing.

Friction counts:

- retyped_gate_flags: 0
- lost_context_or_rebriefs: 0
- manual_status_probes: 2
- approval_confusions: 1
- verification_confusions: 0
- dead_waits_over_30s: 1
- restart_or_recovery_steps: 0

Remaining UI note: the compact follow stop output did not surface the
deferred-verification control as clearly as `mew work --session --resume` and
`mew work --cells` did. The capability works, but the first stop surface may
still be less obvious than the resident cockpit needs.
