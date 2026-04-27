# M6.20 Terminal-Bench Baseline Report

Date: 2026-04-27 JST

Status: baseline recorded; optimization not started.

M6.20 starts from the M6.19 Harbor smoke artifacts. The purpose of this report
is to freeze the initial Terminal-Bench evidence before score optimization: what
was run, where the artifacts live, what scores were observed, what exceptions or
token metadata were available, how failures should be classified through M6.18,
and the first small score/debug target.

## Task List

- Record the M6.19 mew custom-agent Harbor smoke result.
- Record the M6.19 Codex reference-agent Harbor smoke result for the same task
  family.
- Compare scores, errors, exceptions, artifact paths, and token metadata.
- Route the observed zero-score baseline through the M6.18 diagnosis gate before
  any repair or optimization work.
- Set one explicit, bounded score/debug target for the next rerun.

## Environment Notes

- Dataset: `terminal-bench/terminal-bench-2`.
- Smoke task: `terminal-bench/make-mips-interpreter`.
- Trial count: `-n 1` for both mew and Codex smoke runs.
- Limit: `-l 1` for both smoke runs.
- Jobs directory: `proof-artifacts/terminal-bench/harbor-smoke`.
- Mew was invoked through Harbor as a custom agent via
  `mew_terminal_bench_agent:MewTerminalBenchAgent` from `.harbor`.
- The mew smoke mounted the local checkout into the Harbor task container at
  `/mew` and installed it with `python -m pip install -e /mew`.
- The mew compatibility smoke command template was `mew --help`; this proves
  wrapper invocation and clean process return, not task-solving quality.
- The Codex reference smoke used Harbor's built-in `codex` agent with model
  `gpt-5.5` and `reasoning_effort=high`.
- Codex authentication was supplied by `CODEX_AUTH_JSON_PATH=/Users/mk/.codex/auth.json`.

## Commands

Mew custom-agent smoke:

```sh
PYTHONPATH=.harbor harbor run -d terminal-bench/terminal-bench-2 -l 1 -n 1 -y \
  --job-name mew-smoke-help-fixed-return-code \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke \
  --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent \
  --ak install_command="python -m pip install -e /mew" \
  --ak command_template="mew --help" \
  --mounts-json '[{"type":"bind","source":"/Users/mk/dev/personal-pj/mew","target":"/mew"}]'
```

Codex reference-agent smoke:

```sh
CODEX_AUTH_JSON_PATH=/Users/mk/.codex/auth.json harbor run \
  -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/make-mips-interpreter \
  -l 1 \
  -n 1 \
  -y \
  --job-name codex-smoke-make-mips \
  --jobs-dir proof-artifacts/terminal-bench/harbor-smoke \
  --agent codex \
  --model gpt-5.5 \
  --ak reasoning_effort=high
```

M6.19 wrapper validation commands that passed during close:

```sh
uv run pytest -q tests/test_harbor_terminal_bench_agent.py --no-testmon
uv run ruff check .harbor/mew_terminal_bench_agent.py tests/test_harbor_terminal_bench_agent.py
git diff --check
```

## Artifact Paths

Mew Harbor result:

- `proof-artifacts/terminal-bench/harbor-smoke/mew-smoke-help-fixed-return-code/result.json`
- Harbor result id: `deb7b790-c523-4ef9-ad1d-6ccbd9583da8`
- Started: `2026-04-27T12:48:07.113553`
- Finished: `2026-04-27T12:49:44.311009`
- Eval key: `mew__terminal-bench/terminal-bench-2`
- Reward bucket task id: `make-mips-interpreter__4ekDCjP`
- M6.19 transcript note: `command-transcript.json` recorded `exit_code: 0`
- M6.19 artifact root note: Harbor `logs_dir/terminal-bench-harbor-smoke`

Codex Harbor result:

- `proof-artifacts/terminal-bench/harbor-smoke/codex-smoke-make-mips/result.json`
- Harbor result id: `94cf1763-5252-4763-a434-43d58a954b9c`
- Started: `2026-04-27T13:10:25.198393`
- Finished: `2026-04-27T13:19:22.910924`
- Eval key: `codex__terminal-bench/terminal-bench-2`
- Reward bucket task id: `make-mips-interpreter__MomFU8q`
- Agent version from M6.19 close audit: Codex `0.125.0`

## Scores and Exceptions

| Agent | Trials | Errors | Mean score | Reward bucket | Exceptions |
| --- | ---: | ---: | ---: | --- | --- |
| mew custom agent | 1 | 0 | 0.0 | `0.0` | `{}` |
| Codex reference agent | 1 | 0 | 0.0 | `0.0` | `{}` |

Interpretation:

- Both smoke runs completed from Harbor's perspective with zero recorded
  runner errors.
- Both runs scored `0.0` on the selected smoke task.
- Empty `exception_stats` means this baseline is a task-quality/debugging
  problem, not a Harbor execution exception in the recorded result files.
- The mew run currently proves compatibility and artifact capture only. Its
  `mew --help` command template is not an instruction-consuming benchmark
  strategy, so the score is not evidence of the final mew task-solving ceiling.
- The Codex reference run also scored `0.0`, so the first M6.20 target should be
  small and diagnostic rather than broad optimization.

## Token Metadata

Mew smoke:

- The M6.19 close audit records that the compatibility smoke command itself did
  not produce model token usage.
- Optional mew token/cost fields are therefore unavailable for this smoke.

Codex smoke:

- Harbor result token metadata was present according to the M6.19 close audit.
- Input tokens: `2707381`
- Cached input tokens: `2577024`
- Output tokens: `18253`
- Cost: `null`

## Failure Classification Through M6.18

M6.18 closed the implementation-failure diagnosis gate. New failures should be
triaged by scope and routed before repair:

- `polish` -> same-task retry.
- `structural` -> M6.14 repair.
- `invalid task spec` -> task correction.
- `transient` -> retry.
- `ambiguous` -> replay or proof collection before repair.

Current M6.20 baseline classification:

- Harbor runner failure: not observed. Both result files show `n_errors: 0` and
  empty `exception_stats`.
- Benchmark quality failure: observed. Both agents scored `0.0`.
- Mew wrapper compatibility failure: not observed in the M6.19 smoke; the mew
  transcript recorded `exit_code: 0`.
- Mew task-solving failure: ambiguous for this exact smoke, because the mew
  command template was `mew --help` and did not consume the task instructions.
- Reference-agent difficulty signal: present. Codex also scored `0.0` on the
  same selected task, so the selected task may be nontrivial even for the
  reference path.

Route: treat the next M6.20 step as proof/debug collection, not structural M6.14
repair yet. The immediate issue is to establish an instruction-consuming mew
benchmark entrypoint and rerun a bounded task, then classify any remaining
zero-score failure with M6.18 evidence.

## First Explicit Small Score/Debug Target

Before any broad optimization, run one bounded diagnostic rerun whose target is:

> Produce a mew Terminal-Bench artifact for `terminal-bench/make-mips-interpreter`
> that consumes the task instructions rather than `mew --help`, records the
> instruction/command transcript/summary/verifier metadata, exits without Harbor
> exceptions, and improves the mew score from wrapper-only `0.0` to either a
> positive score on the one-task smoke or a classified M6.18 failure with enough
> evidence to choose polish, structural, invalid-spec, transient, or ambiguous
> routing.

Concrete acceptance for the next rerun:

- Keep the rerun bounded to one task and one trial.
- Preserve the same jobs directory family under
  `proof-artifacts/terminal-bench/harbor-smoke` or a clearly named M6.20
  sibling directory.
- Do not chase aggregate benchmark score before the single-task artifact proves
  task-instruction ingestion.
- If the score remains `0.0`, classify the failure through M6.18 using the
  captured transcript and verifier evidence before changing substrate code.

## Baseline Verdict

M6.20 begins from a clean compatibility baseline: Harbor can run mew and Codex,
artifacts are present, both smoke results have zero runner errors and zero
exceptions, and both observed scores are `0.0`. The next work item is not broad
optimization; it is a small instruction-consuming mew rerun with explicit M6.18
failure classification if the score remains zero.
