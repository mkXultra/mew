# M2 Auto-Defer Comparative Dogfood 2026-04-20

Base commit: `4b94316 Auto-defer paired test approvals`

## Goal

Validate whether the paired-test approval auto-defer slice reduces the M2
approval/verification ceremony blocker enough to change the mew-vs-fresh CLI
preference.

## Mew-Side Evidence

Command:

```bash
./mew dogfood --scenario work-session \
  --workspace /tmp/mew-m2-auto-defer-full-dogfood \
  --json
```

Result: `pass`.

Relevant check:

- `work_ai_paired_test_approval_auto_defers_verification`

The dogfood session `#14` in
`/tmp/mew-m2-auto-defer-full-dogfood/.mew/state.json` exercises the paired flow:

- the first source edit triggers `paired_test_steer`
- the tests/** write is coerced to dry-run review
- approving that test write records `verification_deferred=true`
- the source edit is retried after the test approval
- the source approval runs the final verifier with `verification_exit_code=0`

M2 comparative protocol:

```bash
/Users/mk/dev/personal-pj/mew/mew dogfood --scenario m2-comparative \
  --workspace /tmp/mew-m2-auto-defer-full-comparative \
  --mew-session-id 14 \
  --m2-task-shape approval_pairing \
  --json
```

Artifact:

- `/tmp/mew-m2-auto-defer-full-comparative/.mew/dogfood/m2-comparative-protocol.json`

The mew-side evidence has:

- approvals: `total=2`, `applied=2`, `failed=0`
- verification: `passed exit=0`
- continuity: `9/9 strong`
- resume gate: `not_proved`

The resume gate remains `not_proved` because this run did not preserve an
interruption, failure, or recovery risk.

## Fresh CLI Leg

Model: `codex-ultra`

Session: `019da6a4-efe8-7f60-9697-b978bb36bd3c`

Report:

- `/tmp/mew-fresh-auto-defer-comparison.json`

The fresh leg inspected the mew protocol and session artifacts, reran the saved
verifier, reran the focused unit test, and reran the full work-session dogfood.
It did not edit repository files.

Merged protocol:

```bash
/Users/mk/dev/personal-pj/mew/mew dogfood --scenario m2-comparative \
  --workspace /tmp/mew-m2-auto-defer-full-combined \
  --mew-session-id 14 \
  --m2-task-shape approval_pairing \
  --m2-comparison-report /tmp/mew-fresh-auto-defer-comparison.json \
  --json
```

Artifact:

- `/tmp/mew-m2-auto-defer-full-combined/.mew/dogfood/m2-comparative-protocol.json`

Result:

- `comparison_result.status`: `fresh_cli_preferred`
- `next_blocker`: this was a no-edit verification task, not a true
  interruption-shaped M2 parity comparison

## Decision

The auto-defer implementation is validated. It materially reduces the paired
source/test rollback loop that caused prior M2 approval ceremony friction.

It does not close M2. The comparison still favors a fresh CLI for a no-edit
artifact inspection task, and the interruption-resume gate remains `not_proved`.

Next M2 task:

- run a true interruption-shaped process-stop or paired source/test comparative
  dogfood where the mew resident is interrupted mid-flow, resumes without
  rebrief, reaches passing verification, and is compared with a matching fresh
  CLI leg

## Validation

Commands run in the repository:

```bash
uv run ruff check src/mew/commands.py src/mew/work_session.py src/mew/work_cells.py src/mew/dogfood.py tests/test_work_session.py tests/test_dogfood.py
uv run pytest -q tests/test_work_session.py tests/test_dogfood.py
uv run pytest -q
uv run pytest -q tests/test_dogfood.py -k work_session_scenario
./mew dogfood --scenario work-session --workspace /tmp/mew-m2-auto-defer-full-dogfood --json
```

Observed:

- focused dogfood test: `1 passed`
- touched work-session/dogfood tests: `420 passed, 22 subtests passed`
- full suite before the dogfood-extension doc update: `1075 passed, 36 subtests passed`
- work-session dogfood scenario: `pass`
