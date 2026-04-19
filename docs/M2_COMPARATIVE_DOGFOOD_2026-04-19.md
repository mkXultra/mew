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

Resolved UI note: the compact follow stop output originally did not surface the
deferred-verification control as clearly as `mew work --session --resume` and
`mew work --cells` did. Compact `Next CLI controls` now keep
`apply tool #... and defer verification` when pending approvals exist.

## Evidence Pipeline Dogfood

Task: turn the M2 comparative protocol from a hand-filled runbook into a paired
evidence artifact. This adds two executable inputs:

- `--mew-session-id <id>`: prefill the mew side from an actual work session
  with wall/active time, approvals, verification, resume command, and
  continuity.
- `--m2-comparison-report <fresh-cli-report.json>`: merge the fresh CLI side
  from an external agent or human report.

### mew

- Entry: `mew self-improve --start-session ...`, then
  `mew work 246 --follow ...`
- Task/session: task `#246`, work session `#238`
- Result: no additional code change justified on the just-built
  `--mew-session-id` surface
- Summary: mew inspected the builder, formatter, and paired tests, then
  finished with the conclusion that the current surface already covered the
  observer tip, comparison scaffold, and mew-run evidence formatting.

### fresh_cli

- Entry: `codex-ultra` read-only fresh CLI assessment
- Report: `/tmp/mew-fresh-cli-real-report.json`
- Verification: `uv run pytest -q tests/test_dogfood.py -k m2_comparative`
  passed with `3 passed, 48 deselected`
- Result: no additional code blocker found before running a real paired
  comparison

### Combined Artifact

Command:

```bash
./mew dogfood --scenario m2-comparative \
  --workspace /tmp/mew-m2-real-pair \
  --mew-session-id 238 \
  --m2-comparison-report /tmp/mew-fresh-cli-real-report.json \
  --json
```

Result: pass. The generated protocol contained both mew-side work-session
evidence and fresh CLI report evidence. Status remained `inconclusive` because
this was a readiness assessment, not a write-heavy paired coding task.

Follow-up hardening: the fresh CLI assessment noted that `latest` depended on
work-session list order. `--mew-session-id latest` now selects by session
activity timestamp, with a regression test covering out-of-order sessions.

Next useful M2 move: run one real paired coding task through this evidence
pipeline and decide resident preference from that artifact instead of adding
more comparison-surface polish.

## Paired Coding Task: High-Idle Metrics Refactor

Task: deduplicate the high-idle metric calculation so high-idle diagnostic
samples reuse the same wall/active/idle-ratio formula as
`perceived_idle_ratio`.

### mew

- Entry: `mew self-improve --start-session ...`, then
  `mew work 253 --follow ...`
- Task/session: task `#253`, work session `#246`
- Result: completed with supervisor follow-through after mew produced the
  correct reentry checkpoint and small-change recommendation
- Verification:
  - `uv run pytest --testmon -q tests/test_metrics.py -k 'high_idle or latency or retire_historical_friction'`
  - full `uv run pytest -q`
- Summary: mew found the right metrics/test surface, inspected the relevant
  windows, and recorded a durable recommendation. The implementation was then
  applied with that context. Continuity was strong (`9/9`) and the work session
  produced a usable resume command, but the task still required supervisor
  execution rather than being completed end-to-end inside the cockpit.

### fresh_cli

- Entry: `codex-ultra` in detached worktree `/tmp/mew-fresh-high-idle`
- Report: `/tmp/mew-fresh-cli-high-idle-comparison.json`
- Verification:
  - `uv run pytest -q tests/test_metrics.py` (`6 passed`)
  - `uv run ruff check src/mew/metrics.py tests/test_metrics.py`
- Summary: fresh CLI completed the same localized refactor directly with
  minimal friction. Its only minor issue was using `uv run python` after
  `python` was not on PATH for report validation.

### Combined Artifact

Command:

```bash
./mew dogfood --scenario m2-comparative \
  --workspace /tmp/mew-m2-session-246-paired \
  --mew-session-id 246 \
  --m2-comparison-report /tmp/mew-fresh-cli-high-idle-comparison.json \
  --json
```

Result: pass. The generated protocol merged both mew-side work-session
evidence and the fresh CLI report. The comparison status was
`fresh_cli_preferred`.

Follow-up: for small localized changes, mew still has too much observer
overhead versus a fresh CLI. The next useful paired task should either be
write-heavy enough for mew's persistent context to matter, or should reduce the
supervision overhead for small local changes.

## Interruption-Resume Gate Protocol

After the scoped M3 reentry gate was added, the M2 comparative artifact was
extended with an explicit `interruption_resume_gate` section. This keeps the
next paired task from drifting into another generic speed comparison.

The protocol now records:

- `task_shape.recommended_next=interruption_resume`
- required mew evidence: changed/pending work, preserved risk or interruption,
  runnable next action, usable continuity, and passing verification after
  reentry
- required fresh CLI evidence: whether manual rebrief was needed, whether
  files/risks/next action had to be reconstructed, and whether verification
  completed with less supervision
- per-run `interruption_resume_gate.mew` and `.fresh_cli` fields, so external
  model reports can be merged into the same JSON artifact

Validation:

- `uv run python -m py_compile src/mew/dogfood.py tests/test_dogfood.py`
- `uv run pytest --testmon -q tests/test_dogfood.py -k "m2_comparative or m3_reentry_gate"`
- `uv run ruff check src/mew/dogfood.py tests/test_dogfood.py`
- `./mew dogfood --scenario m2-comparative --workspace /tmp/mew-m2-interruption-protocol --json`

Next useful M2 move: run a real interruption-shaped paired coding task, then
merge both sides with:

```bash
mew dogfood --scenario m2-comparative \
  --mew-session-id <id> \
  --m2-comparison-report <fresh-cli-report.json>
```

## Paired Coding Task: M2 Task Shape Option

Task: add an explicit `--m2-task-shape` option to
`mew dogfood --scenario m2-comparative` so interruption-shaped paired runs can
set `task_shape.selected` without hand-editing the generated protocol.

### mew

- Entry: `mew self-improve --start-session --force ...`, then
  `mew work 254 --live ... --max-steps 1` and
  `mew work 254 --follow ... --max-steps 10`
- Task/session: task `#254`, work sessions `#247` and `#248`
- Result: did not complete the implementation inside mew
- Resume behavior:
  - `mew work 254 --session --resume --allow-read .` restored the work thread
    without a user rebrief
  - continuity was strong (`9/9`)
  - the resume bundle preserved touched files, failed step, pending steer,
    world state, active project memory, and a concrete next action
- Blocking gap: the model correctly narrowed from `src/mew/dogfood.py` to
  `src/mew/cli.py` after an interrupt-submit steer, then hit paired-test
  steering and attempted to inspect `tests/test_cli.py`, which does not exist.
  It stopped with no passing verification candidate.

Mew-side gate evidence from the combined artifact:

- `changed_or_pending_work=true`
- `risk_or_interruption_preserved=true`
- `runnable_next_action=true`
- `continuity_usable=true`
- `verification_after_resume_candidate=false`
- `interruption_resume_gate.mew.status=not_proved`

### fresh_cli

- Entry: `codex-ultra` in detached worktree `/tmp/mew-fresh-task-shape`
- Report: `/tmp/mew-fresh-task-shape-report.json`
- Result: completed the small parser/protocol/test change directly
- Verification:
  - `uv run pytest -q tests/test_dogfood.py -k m2_comparative`
  - `uv run pytest -q tests/test_dogfood.py -k "m2_comparative or m2_task_shape"`
  - `uv run ruff check src/mew/dogfood.py src/mew/cli.py tests/test_dogfood.py`
  - `uv run python -m py_compile src/mew/dogfood.py src/mew/cli.py tests/test_dogfood.py`
  - `./mew dogfood --scenario m2-comparative --m2-task-shape interruption_resume --workspace /tmp/mew-fresh-task-shape/.tmp/m2-cli-smoke --json`
- Summary: fresh CLI added the task-shape choices, CLI flag, dispatch wiring,
  protocol selection, and focused tests with no approval or verification
  confusion. However, this fresh run was not actually interrupted mid-task, so
  it does not prove the interruption-resume gate either.

### Combined Artifact

Command:

```bash
./mew dogfood --scenario m2-comparative \
  --workspace /tmp/mew-m2-task-shape-combined \
  --mew-session-id 248 \
  --m2-task-shape interruption_resume \
  --m2-comparison-report /tmp/mew-fresh-task-shape-report.json \
  --json
```

Artifact:

- `/tmp/mew-m2-task-shape-combined/.mew/dogfood/m2-comparative-protocol.json`

Result: pass. The generated protocol merged both mew-side work-session evidence
and fresh CLI report evidence. The comparison status was `inconclusive`.

Comparison result:

- `comparison_result.status=inconclusive`
- `resident_preference.choice=inconclusive`
- mew was better at preserving resident continuity after interruption, but did
  not complete the implementation or verification
- fresh CLI completed the implementation smoothly, but did not exercise a real
  interruption/resume path

Follow-up: the next M2 comparison should be a true interrupted-resume trial on
both sides, or mew should reduce the paired-test steering failure where it
suggested a non-existent `tests/test_cli.py` instead of finding the existing
`tests/test_dogfood.py` parser coverage.
