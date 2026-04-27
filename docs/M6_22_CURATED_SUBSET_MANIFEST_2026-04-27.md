# M6.22 Curated Subset Manifest

Date: 2026-04-27 JST

Status: subset selected, all task runs recorded; first repair candidate selected.

## Source

- Registry:
  `docs/data/terminal_bench_2_codex_0_121_0_gpt_5_5_openai.json`
- Subset JSON:
  `docs/data/terminal_bench_m6_22_curated_subset.json`
- Run ledger:
  `docs/M6_22_CURATED_SUBSET_RUNS_2026-04-27.md`
- Reference: Terminal-Bench 2.0 Codex `0.121.0` / `gpt-5.5@openai`

## Selection

M6.22 uses one task from each non-100% Codex band plus both M6.20 fixed-gate
tasks as 100% positive controls.

| Band | Task | Codex target |
|---:|---|---:|
| 0% | `filter-js-from-html` | 0/5 |
| 20% | `sanitize-git-repo` | 1/5 |
| 40% | `gcode-to-text` | 2/5 |
| 60% | `overfull-hbox` | 3/5 |
| 80% | `extract-elf` | 4/5 |
| 100% | `cancel-async-tasks` | 5/5 |
| 100% | `fix-code-vulnerability` | 5/5 |

Aggregate Codex target: **20/35 successes, 57.14%**.

## Rationale

- `filter-js-from-html`: 0% band, useful for failure classification without
  treating every red task as a regression.
- `sanitize-git-repo`: 20% band, stresses repository mutation and command
  policy in an arbitrary workspace root.
- `gcode-to-text`: 40% band, stresses parsing and output verification.
- `overfull-hbox`: 60% band, medium document/build task; selected instead of
  `make-mips-interpreter` because that task remains a noisy stretch candidate.
- `extract-elf`: 80% band, binary/file inspection and artifact verification.
- `cancel-async-tasks` and `fix-code-vulnerability`: 100% positive controls
  already proven by M6.20 current-head runs.

## Execution Rule

Use the same generic command shape as M6.20:

```sh
mew work --oneshot --instruction {instruction_shell} --cwd /app --allow-read . --allow-write . --allow-shell --approval-mode accept-edits --defer-verify --no-prompt-approval --auth /codex-auth/auth.json --model-backend codex --model gpt-5.5 --model-timeout 300 --max-steps 30 --report {report_path} --artifacts {artifact_dir} --json
```

Do not add a Terminal-Bench-specific solver path. Harness glue may mount auth,
set `/app` as cwd, and collect reports, but implementation must stay on the
normal work-session path.

## Done-When Mapping

- Manifest exists with task names, checksums, Codex targets, and selection
  rationale: satisfied by this document and the JSON manifest.
- Current action: implement the selected generic repair and rerun the
  below-target `overfull-hbox` task.
- Runs recorded so far: `filter-js-from-html` completed 0/5 with 5
  `VerifierTimeoutError` exceptions, matching the 0/5 Codex target;
  `sanitize-git-repo` completed 1/5 with Harbor errors 0, matching the 1/5
  Codex target; `gcode-to-text` completed 0/5 with 1 `AgentTimeoutError`,
  below the 2/5 Codex target and classified in the run ledger;
  `overfull-hbox` completed 1/5 with Harbor errors 0, below the 3/5 Codex
  target and classified in the run ledger; `extract-elf` completed 5/5 with
  Harbor errors 0, exceeding the 4/5 Codex target.
- Full subset total, including the M6.20 positive controls: mew 17/35 versus
  Codex target 20/35.
- Selected first repair route: generic acceptance-constraint ledger / final
  self-check before finish, using `overfull-hbox` as the rerun proof.
- Any below-target mew task must be classified through M6.18 before repair.
