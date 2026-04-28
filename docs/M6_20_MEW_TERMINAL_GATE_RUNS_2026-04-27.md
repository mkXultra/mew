# M6.20 Mew Terminal Gate Runs

Date: 2026-04-27 JST

Status: fixed two-task terminal gate reached on current head.

## Command Shape

Both final gate runs used the generic `mew work --oneshot` implementation path
through Harbor. No Terminal-Bench-specific solver path was added to mew core.

```sh
env PYTHONPATH=.harbor harbor run \
  -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/<task-name> \
  -k 5 \
  -n 5 \
  -y \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke \
  --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent \
  --ak install_command='python -m pip install -e /mew' \
  --ak command_cwd=/app \
  --ak command_template='mew work --oneshot --instruction {instruction_shell} --cwd /app --allow-read . --allow-write . --allow-shell --approval-mode accept-edits --defer-verify --no-prompt-approval --auth /codex-auth/auth.json --model-backend codex --model gpt-5.5 --model-timeout 300 --max-steps 30 --report {report_path} --artifacts {artifact_dir} --json' \
  --mounts-json '[{"type":"bind","source":"/Users/mk/dev/personal-pj/mew","target":"/mew"},{"type":"bind","source":"/Users/mk/.codex/auth.json","target":"/codex-auth/auth.json"}]'
```

## Final Gate Results

### `terminal-bench/cancel-async-tasks`

- Job: `mew-work-oneshot-cancel-async-tasks-5attempts-boundary-verifier-20260427-2201`
- Result:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-work-oneshot-cancel-async-tasks-5attempts-boundary-verifier-20260427-2201/result.json`
- Trials: 5
- Harbor errors: 0
- Mean: 1.000
- Pass@5: 1.000
- Rewards: 5 successes, 0 failures

### `terminal-bench/fix-code-vulnerability`

- Job: `mew-work-oneshot-fix-code-vulnerability-5attempts-current-head-20260427-2207`
- Result:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-work-oneshot-fix-code-vulnerability-5attempts-current-head-20260427-2207/result.json`
- Trials: 5
- Harbor errors: 0
- Mean: 1.000
- Pass@5: 1.000
- Rewards: 5 successes, 0 failures

## Repair Sequence

The gate did not pass immediately. The useful failure sequence was:

1. `fix-code-vulnerability` initially reached the correct patch but stopped at
   pending approval. Repair: run the generic work path with
   `--approval-mode accept-edits --defer-verify --no-prompt-approval` for
   external-harness verification.
2. `cancel-async-tasks` exposed that accept-edits did not propagate
   `--defer-verify` through all write paths. Repair: batch approval, single
   approval, and direct applied writes now preserve the CLI defer flag.
3. A later `cancel-async-tasks` attempt failed by reading missing `/app/run.py`
   and stopping. Repair: missing `read_file` under an allowed write root is
   recoverable when more steps remain, so the next model turn can create the
   file.
4. Remaining failures were verifier-planning gaps around process-level
   cancellation and concurrency boundaries. Repair: work prompts now require
   process-level cancellation/interrupt checks when the task mentions
   `KeyboardInterrupt`, `Ctrl-C`, `SIGINT`, cancellation, or cleanup, and require
   below/equal/above boundary coverage for cancellation-sensitive concurrency
   limits when practical.

## M6.18 Classification

- Approval policy mismatch: fixed by explicit accept-edits/defer command shape
  and defer propagation.
- Generic work-session substrate issue: fixed direct applied-write defer and
  recoverable missing create-target read.
- Verifier-planning weakness: fixed by stronger generic cancellation and
  concurrency-boundary verifier guidance.
- Terminal-Bench-specific solver drift: not introduced.

## Validation

Focused local validation passed:

```sh
uv run pytest -q tests/test_work_session.py -k 'recovers_missing_read_file_under_write_root or work_think_prompt_guides_independent_reads_to_batch or direct_applied_write_can_defer_verification_without_command or accept_edits or defer_verification_without_command'
uv run ruff check src/mew/commands.py src/mew/work_loop.py tests/test_work_session.py
```

Observed result: focused pytest `12 passed, 687 deselected`; ruff passed.
