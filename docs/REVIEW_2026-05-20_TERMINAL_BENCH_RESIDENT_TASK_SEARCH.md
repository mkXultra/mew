# Terminal-Bench / Harbor Resident-Advantage Task Search

Date: 2026-05-20 JST

## STATUS: PARTIAL

No existing Terminal-Bench task was found that directly measures resident-agent
advantage: repeated invocations, cross-session persistence, durable memory
reuse, reentry after failure, or learning from prior repairs. Harbor does have
task-format support that can be adapted for this: multi-step tasks with shared
trial environment, per-step instructions/tests, per-step artifacts, and
trial-level reward aggregation.

## Existing Evidence

### Actual Terminal-Bench tasks already measuring this

Not found.

Evidence:

- `docs/data/terminal_bench_2_codex_0_121_0_gpt_5_5_openai.json` records
  Terminal-Bench 2.0 Codex baseline metadata with `task_count: 89`. Keyword scan
  of task names for `memory|session|resident|reentry|multi|repeat|continual`
  found only `custom-memory-heap-crash`, `git-multibranch`, and
  `multi-source-data-merger`.
- Public Terminal-Bench 2.0 lists 89 tasks:
  `https://www.tbench.ai/benchmarks/terminal-bench-2`.
- The matching keyword tasks are normal one-shot task goals, not resident
  persistence tasks:
  - `custom-memory-heap-crash` is C++ memory-management debugging:
    `https://www.tbench.ai/benchmarks/terminal-bench-2/custom-memory-heap-crash`
  - `multi-source-data-merger` is ETL/schema merging:
    `https://www.tbench.ai/benchmarks/terminal-bench-2/multi-source-data-merger`
  - `git-multibranch` is Git server deployment:
    `https://www.tbench.ai/benchmarks/terminal-bench-2/git-multibranch`
- Terminal-Bench task docs describe one task description plus final-state tests,
  with optional multiple descriptions for difficulty levels, not repeated agent
  calls or persisted cross-session state:
  `https://www.tbench.ai/docs/task-overview`.
- Terminal-Bench agent docs expose a single `perform_task(task_description,
  session, logging_dir)` style entrypoint:
  `https://www.tbench.ai/docs/agent-introduction`.

### Task framework support that could be adapted

Found in Harbor, not classic Terminal-Bench.

Evidence:

- Harbor migration docs say Harbor is an iteration on Terminal-Bench format and
  provides migration from Terminal-Bench task directories:
  `https://www.harborframework.com/docs/migration`.
- Harbor multi-step tasks run ordered steps against one shared environment, with
  separate instruction, tests, setup, and verifier result per step. The docs
  explicitly say this is useful for continual-learning methods like memory and
  for observing whether an agent builds on prior work:
  `https://www.harborframework.com/docs/tasks/multi-step`.
- Harbor multi-step tasks can preserve files across steps, gate later steps via
  `min_reward`, select `mean` or `final` reward aggregation, and collect
  per-step artifacts:
  `https://www.harborframework.com/docs/tasks/multi-step`.
- Harbor task docs support `/logs/agent/`, `/logs/verifier/`, reward files, and
  explicit artifacts such as `/logs/agent/trajectory.json` for trajectory
  grading:
  `https://www.harborframework.com/docs/tasks`.

### Local mew evidence

- `ROADMAP.md:1461` defines M6.25 as Codex-Plus Resident Advantage, requiring
  persistence, memory, reentry, diagnosis, repair loops, and repeated-work
  benefit from previous failures.
- `docs/M6_25_RESIDENT_ADVANTAGE_PLAN_2026-05-20.md` already frames Phase 1 as
  a cold-vs-resident comparison and names `reshard-c4-data`, `pypi-server`, and
  `merge-diff-arc-agi-task` as candidate repair-reuse evidence.
- `docs/SIDE_PROJECT_HARBOR_RESIDENT_MEMORY_BENCH.md` already proposes a
  three-phase Harbor task family: seed, recall, and stale/misleading memory.
  It also specifies metrics such as `memory_mode`, `first_edit_latency_seconds`,
  `memory_items_injected`, and `stale_memory_rejected`.
- `docs/terminal-bench-harbor-smoke.md` shows the current mew Harbor wrapper is
  one instruction-consuming custom-agent run per task, with artifacts such as
  `instruction.json`, `command-transcript.json`, `mew-report.json`, and
  `summary.json`.
- `docs/M6_24_STAGED_CLOSE_REPORT_2026-05-20.md` says M6.24 should stop
  reflexive proof collection and move to M6.25 resident advantage.

## Candidate Task Shape

Smallest Harbor-compatible resident-advantage task:

1. Build a Harbor multi-step task named something like
   `mew/resident-golden-convention-recall`.
2. Use one tiny Python package in `/app` with deterministic tests and no network.
3. Step A, seed:
   - Instruction asks for a small feature.
   - Correct solution requires discovering a project convention, for example
     implementation under `src/` plus golden verifier under `tests/golden/`.
   - A tempting direct unit test is insufficient or misleading.
   - Step verifier checks correctness and expects the agent to emit a compact
     memory/trajectory artifact under `/logs/artifacts/` or `/logs/agent/`.
4. Step B, recall:
   - Similar but not identical feature in the same task family.
   - A resident/memory-enabled agent should use the Step A convention faster.
   - A cold agent can still solve it, but should take more reads/searches or
     repeat the rejected path.
5. Step C, stale memory:
   - Provide one stale memory hint, for example old golden path moved to a new
     verifier path.
   - Correct behavior is to verify the memory against the current workspace
     before relying on it.
6. Reward:
   - Use `multi_step_reward_strategy = "final"` if Step C includes a full
     end-to-end verifier, or `mean` if each step is independently meaningful.
   - Emit `reward.json` with correctness plus measurement fields.
7. Artifacts:
   - Collect `/logs/agent/trajectory.json` or mew's report artifact.
   - Collect the final changed package files and a metrics JSON with
     `memory_mode`, first edit latency, read/search/tool counts, verifier count,
     memory refs injected/used, and stale-memory rejection.

Comparison protocol:

- Run `memory_off` baseline.
- Run `memory_on` current mew baseline.
- Run `stale_memory` current mew baseline.
- Compare pass rate, first-edit latency, read/search/tool counts, verifier count,
  and stale-memory rejection. Do not change mew memory behavior before these
  baselines exist.

## Recommended Next Action For M6.25

Create the M6.25 experiment ledger first, then choose one of two paths:

1. Fastest M6.25 evidence path: run the planned cold-vs-resident comparison on
   an existing Terminal-Bench-shaped task such as `reshard-c4-data`, using local
   mew memory/reentry instrumentation. This is lower setup cost but is not a
   clean benchmark task.
2. Better benchmark path: implement the minimal Harbor multi-step
   `resident-golden-convention-recall` task before running M6.25 memory
   experiments. This is the smallest task shape that directly measures resident
   advantage rather than inferring it from repeated one-shot Terminal-Bench runs.

Recommendation: build the small Harbor multi-step task before claiming M6.25
resident advantage. Existing Terminal-Bench tasks can still provide regression
checks, but they should not be treated as the primary resident-memory benchmark.

## Risks / Unknowns

- Harbor multi-step support is public and documented, but mew's checked-in
  Terminal-Bench wrapper is currently documented and tested around one
  instruction-consuming task run. It may need a wrapper/artifact-path check for
  step identity before using multi-step artifacts as evidence.
- A single shared Harbor environment across steps measures within-trial
  continuity. True cross-session resident memory may require running separate
  trials with an external memory seed/import step, or adding a task wrapper that
  invokes the agent multiple times with persisted external state.
- If Step B is too similar to Step A, the task will measure duplicate-task
  shortcutting rather than reusable repair memory. If too different, memory
  will not help.
- Stale-memory scoring must be artifact/test based, not prose based, or agents
  can claim rejection without doing the verification.
- Built-in Terminal-Bench leaderboard comparability will be limited for a custom
  Harbor task; use it as M6.25 resident-advantage evidence, not M6.24 parity
  evidence.
