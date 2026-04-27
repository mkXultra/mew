# M6.22 Curated Subset Runs

Date: 2026-04-27 JST

Status: first selected task run recorded.

## Scope

M6.22 uses the fixed curated subset in
`docs/data/terminal_bench_m6_22_curated_subset.json`.

Codex registry target for the full curated subset: **20/35 successes**.

This document records mew results as they are run through the same generic
`mew work --oneshot` Harbor command shape used by M6.20. It must not become a
Terminal-Bench-specific solver log.

## Results

| Task | Codex target | Mew result | Harbor errors | Runtime | Artifact |
|---|---:|---:|---:|---:|---|
| `filter-js-from-html` | 0/5 | 0/5 | 5 | 32m 24s | `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-filter-js-from-html-5attempts-20260427-2207/result.json` |

Current counted subset total: **0/5**, matching the 0/5 Codex target for the
only counted M6.22 task run so far.

Positive controls from M6.20 remain available but are not re-counted in this
document until the five not-yet-run M6.22 tasks finish:

- `cancel-async-tasks`: mew 5/5, Codex target 5/5
- `fix-code-vulnerability`: mew 5/5, Codex target 5/5

## `filter-js-from-html`

Command shape:

```sh
mew work --oneshot --instruction {instruction_shell} --cwd /app --allow-read . --allow-write . --allow-shell --approval-mode accept-edits --defer-verify --no-prompt-approval --auth /codex-auth/auth.json --model-backend codex --model gpt-5.5 --model-timeout 300 --max-steps 30 --report {report_path} --artifacts {artifact_dir} --json
```

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-22-filter-js-from-html-5attempts-20260427-2207/result.json`

Observed result:

- `n_total_trials`: 5
- `n_trials`: 0
- `n_errors`: 5
- `exception_stats`: `VerifierTimeoutError` for all 5 trials
- `mean`: 0.0
- `pass@5`: 0.0
- started: `2026-04-27T22:07:22.268417`
- finished: `2026-04-27T22:39:46.498522`

Trial notes:

- Each trial produced a `mew-report.json`.
- All five work reports reached `stop_reason = finish`.
- The work reports show zero accepted writes for this task, so this run is best
  classified as a no-edit / verifier-timeout result, not a failed patch.
- The cached verifier runs Selenium/Chrome tests and timed out after 900s.
- Harbor's Docker cleanup failed afterward because the five task containers did
  not emit exit events when stopped. A manual `docker rm -f` attempt against the
  five Harbor container IDs returned the same daemon exit-event failure.

Classification:

- Against the frozen Codex target: no parity gap for this task, because Codex
  target is 0/5.
- Against implementation-lane usefulness: keep as cost/no-op evidence. It does
  not justify a core repair by itself because the reference target is also 0/5.
- Harness note: the stuck Docker containers are environmental cleanup debt, not
  mew core evidence unless it recurs on non-Selenium tasks.

## Next Tasks

Run the remaining non-control M6.22 tasks:

1. `sanitize-git-repo` (Codex target 1/5)
2. `gcode-to-text` (Codex target 2/5)
3. `overfull-hbox` (Codex target 3/5)
4. `extract-elf` (Codex target 4/5)

If any task lands below the Codex target, classify it through M6.18 before
choosing a repair.
