# [side-pj] mew-companion-log: scaffold blocked by core write-scope guard

## Side Project And Task

- Side project: `mew-companion-log`
- Task: `#1` / session `#1`
- Summary: SP1 scaffold should create `README.md`, a runnable fixture-driven markdown CLI/script, a fixture JSON, and focused tests under `experiments/mew-companion-log`.
- Expected role: Codex CLI as `operator`; mew as first implementer.

## Commands Used

```bash
./mew work 1 --follow --allow-read experiments/mew-companion-log --allow-write experiments/mew-companion-log --allow-verify --verify-command "uv run pytest -q experiments/mew-companion-log" --approval-mode accept-edits --compact-live --max-steps 10 --quiet
./mew work 1 --steer "Use model gpt-5.5 for implementation. This is a side-project scaffold, not a core mew src/mew patch. The valid paired product paths are under experiments/mew-companion-log, including companion_log.py or package files plus tests/test_companion_log.py and README/fixtures. Do not edit src/mew. Treat the declared write root experiments/mew-companion-log as the full product scope for this attempt."
./mew work 1 --follow --model-backend codex --model gpt-5.5 --allow-read experiments/mew-companion-log --allow-write experiments/mew-companion-log --allow-verify --verify-command "uv run pytest -q experiments/mew-companion-log" --approval-mode accept-edits --act-mode deterministic --compact-live --quiet --max-steps 10
```

## What Mew Attempted

- Inspected `experiments/mew-companion-log`.
- Observed the target directory was empty.
- Planned scaffold files under `experiments/mew-companion-log`:
  `companion_log.py`, `tests/test_companion_log.py`,
  `fixtures/sample_session.json`, and `README.md`.
- After explicit gpt-5.5 steer, again treated those paths as the target scope.

## Failure Evidence

Both write attempts stopped before applying product files with:

```text
write batch is limited to write/edit tools under tests/** and src/mew/** with at least one of each
```

Focused verifier did not run because no product files were written.

## Why The Operator Stopped

This repeated after one focused steering attempt and appears to be a core
write-ready/compiler substrate assumption that only accepts core mew
`src/mew/**` plus root `tests/**` paired patches. The side-project task cannot
complete honestly without operator product-code edits, which would violate
mew-first credit.

## Classification

- Looks like: M6.14 repair candidate and M6.16 implementation-lane hardening input
- Failure class:
  `side_project_write_scope_guard_rejected_experiments_paths`
- Ledger row: `proof-artifacts/side_project_dogfood_ledger.jsonl` row `1`
- Local report:
  `experiments/mew-companion-log/.mew-dogfood/reports/1-scaffold-write-scope-guard-blocked.json`
