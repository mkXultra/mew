# Resident-Agent Benchmark Frameworks - 2026-05-20

STATUS: PARTIAL

There is no clean public equivalent of "Terminal-Bench for resident coding
advantage" that directly measures interruption reentry, memory reuse, repeated
failure avoidance, and local terminal/container execution in one package.

The closest practical path is to keep Harbor / Terminal-Bench as the execution
substrate and add a small multi-step, multi-invocation resident-memory task
family. Harbor now has a first-class multi-step task format, while newer memory
benchmarks provide the concepts and metrics for warm/cold memory comparisons.

## Candidate Frameworks And Relevance

| Candidate | What it measures | Persistence / repeated invocation | Practical fit for mew M6.25 |
|---|---|---|---|
| Harbor multi-step tasks / Terminal-Bench | Real terminal tasks in containers, scored by verifier scripts and reward files. Terminal-Bench supplies realistic CLI tasks; Harbor supplies the task/run format. | Harbor multi-step tasks run ordered steps against one shared environment, with per-step instructions, tests, setup hooks, reward aggregation, early stopping, and artifacts. Harbor docs explicitly call out memory and continual-learning methods as a use case. It does not, by itself, define host-side durable memory, cold/warm A/B, or process-stop reentry. | Best local substrate. Mew already proved Harbor custom-agent compatibility in `docs/M6_19_TERMINAL_BENCH_COMPATIBILITY_AUDIT_2026-04-27.md`. Use Harbor for containers, verifiers, and artifacts; add a thin outer runner or agent wrapper for memory-off/memory-on/stale-memory conditions. |
| STATE-Bench | Agentic memory on realistic enterprise tasks with tools, user simulator, deterministic state checks, task completion, pass^5 reliability, UX, and cost. | Clean "bring your own memory" interface: train trajectories are used to extract reusable learnings, then test tasks call `retrieve_learnings(...)`. Compares memory benefit against no-memory runs over five attempts. | Strongest metric template for memory value. Not coding or terminal-first, and official testing appears locked to its task loop/model protocol, so adapt concepts rather than port mew into it immediately. |
| MemoryArena | Multi-session agentic memory in interdependent subtasks. The point is not recall alone, but using earlier interaction feedback to solve later tasks. | Very clean episode/subtask shape: each row contains multiple questions/subtasks and answers; later subtasks depend on information learned earlier. | Strong schema reference for "episode 1 / episode 2 with persisted memory." Not a local terminal/coding harness; use as conceptual design for task chaining and distractor/stale-memory tests. |
| LongMemEval-V2 | Long-term agent memory over web-agent trajectories. Tests static state recall, dynamic state tracking, workflow knowledge, environment gotchas, premise awareness, answer accuracy, and latency. Includes memory backend hooks and a Codex baseline. | Memory backends ingest many trajectories and return compact evidence. It is retrieval/QA over histories, not active repair execution, but it directly names recurring gotchas and workflow knowledge. | Useful taxonomy for M6.25 memory items: workflow, gotcha, stale premise, dynamic state. Not enough as the benchmark because it lacks local patch/test execution. |
| SWE-Bench-CL | Continual learning for coding agents over chronologically ordered SWE-Bench issues. Metrics include accuracy, forgetting, forward/backward transfer, tool-use efficiency, and composite continual-learning scores. | Directly compares memory-enabled and memory-disabled agents across issue sequences. Evaluates transfer and catastrophic forgetting. | Strong coding-specific reference for sequential issue streams and transfer metrics. Less practical than Harbor for mew because it inherits SWE-Bench setup rather than the existing Terminal-Bench/Harbor path. |
| SWE-CI | Repository maintenance via repeated CI loops: run tests, derive requirements, modify code. Measures sustained maintainability rather than one-shot correctness. | Multi-iteration loop over repository evolution. It is about long-term code quality and regressions, not explicit resident memory. | Useful for "repair over time" scoring ideas, especially normalized progress/regression metrics. Too heavy for the first M6.25 proof. |
| SWE-Chain | Chained release-level package upgrades where each transition builds on the prior codebase. | Clean chain semantics: the agent-modified package state from transition N becomes input to N+1. | Very relevant to resident coding continuity, but too new and larger than needed. Borrow the "previous modified codebase is the next initial state" rule. |
| CLIN / Reflexion | Trial-to-trial improvement without model weight updates through textual memory or reflective episodic memory. Includes repeated trials and learning from feedback. | Explicitly stores lessons after trials and reuses them in subsequent trials. Focuses on avoiding repeated mistakes and improving over retries. | Good behavioral primitive for "repair memory": after a failed verifier, write a compact cause/fix memory and prove the next same-shape run avoids the failure. Not a ready local benchmark harness. |
| continuity-benchmarks | Community coding-agent memory benchmark for structured retrieval/action alignment over fictional codebase histories and LongMemEval-S. | Compares no retrieval, blanket retrieval, and targeted retrieval; includes seven noisy sessions and custom retrieval adapters. | Small, coding-memory-specific, and cheap. It measures retrieval/action alignment rather than terminal task completion, so it is a side reference rather than the M6.25 proof harness. |
| tau-bench / AppWorld / OSWorld / AgentBench | Multi-turn tool use, app/world interaction, GUI/OS tasks, and broad agent skills. | Mostly in-episode state tracking. Some use pass^k reliability or realistic simulators, but not durable memory across coding sessions. | Useful negative controls: they show multi-turn interaction is not the same as resident advantage. Borrow pass^k and simulator rigor only where helpful. |

## Comparison To Terminal-Bench

Terminal-Bench is still the best match for mew's current implementation lane:
real terminal work, Docker execution, hidden or external verifiers, and
side-by-side comparison against Codex-style agents. Its default task model,
however, treats trials as independent attempts. That is good for one-shot
terminal parity, but weak for M6.25 because resident advantage should appear
between invocations.

Harbor closes part of that gap. Its multi-step task format supports ordered
steps in one shared environment, per-step verifiers, early stopping, artifacts
after each step, and trial-level rollup. That is enough to express:

- seed step: agent discovers a convention or failure mode;
- recall step: similar task should benefit from the prior discovery;
- stale step: injected memory is wrong or obsolete and must be verified before use.

The missing piece is not the container or verifier format. It is the evaluation
condition: Harbor does not standardize "same resident memory across calls" vs
"fresh cold agent" vs "stale memory injection." Mew should add that at the
wrapper/campaign layer, not by changing core benchmark semantics.

## Clean Concept Check

| Desired concept | Found? | Best source |
|---|---|---|
| Episode 1 / episode 2 with persisted memory | Yes, conceptually; partial in local terminal harness. | MemoryArena, STATE-Bench, SWE-Bench-CL; Harbor multi-step can host a local version. |
| Cold vs warm/reentry comparison | Yes for memory-on/off; weaker for interruption reentry. | STATE-Bench, SWE-Bench-CL, continuity-benchmarks; mew's local M2 process-stop dogfood has task-chain reentry evidence. |
| Repair reuse / avoiding known failure | Yes conceptually; rare as terminal coding benchmark criterion. | CLIN, Reflexion, LongMemEval-V2 "environment gotchas", mew `docs/M6_14_STRUCTURAL_REPAIR_LEDGER.md`. |
| Local-first terminal/container execution | Yes. | Harbor / Terminal-Bench; SWE-CI also uses Docker but is heavier and less aligned with current mew artifacts. |

No single framework has all four. Harbor has the execution substrate; memory
benchmarks have the resident-state measurement ideas.

## What To Borrow For Mew M6.25

Borrow from Harbor:

- multi-step tasks with per-step verifier results;
- shared environment files for within-trial continuity;
- per-step artifacts for transcript, diff, memory snapshot, and verifier output;
- reward JSON instead of prose-only grading.

Borrow from STATE-Bench:

- memory-off baseline before memory-on improvements;
- pass^k / pass^5 reliability, not only pass@1;
- task completion, cost/latency, and user-burden metrics as separate dimensions;
- memory as pluggable behavior, isolated from benchmark plumbing.

Borrow from MemoryArena:

- subtasks that are interdependent but not duplicates;
- distractor or irrelevant prior sessions so memory selectivity is measured;
- later subtasks that require applying earlier discovered constraints.

Borrow from LongMemEval-V2:

- explicit memory categories: workflow knowledge, environment gotchas, dynamic state, stale premise awareness;
- latency/cost for retrieval as first-class metrics;
- compact evidence returned by a memory backend rather than raw full-history replay.

Borrow from SWE-Bench-CL / SWE-Chain / SWE-CI:

- chronological task streams;
- forward/backward transfer and forgetting/regression metrics;
- previous agent-modified state becoming the next task's starting state;
- CI/test progress as a continuous score, not only final success.

Borrow from mew local docs:

- `docs/SIDE_PROJECT_HARBOR_RESIDENT_MEMORY_BENCH.md` already has the right Phase A/B/C shape and metric fields.
- `docs/M2_PROCESS_STOP_COMPARATIVE_DOGFOOD_2026-04-20.md` proves mew can evaluate task-chain reentry across interrupted work sessions.
- `docs/M6_14_STRUCTURAL_REPAIR_LEDGER.md` already records same-shape failures and generic repairs; this can seed repair-reuse task families.
- `ROADMAP.md` M6.25 requires equal-or-better Terminal-Bench quality plus evidence for persistence, memory, reentry, diagnosis, repair reuse, auditability, and user burden.

## Proposed Minimal Benchmark Schema

Use Harbor as the task format and add an outer resident campaign manifest:

```yaml
schema_version: resident-bench-v0
task_family: golden-convention-recall
base_harness: harbor
execution:
  environment: docker
  verifier: deterministic_tests
  network: disabled
conditions:
  - id: cold
    memory_mode: off
    memory_seed: none
    workspace_reset: true
  - id: warm
    memory_mode: on
    memory_seed: phase_a_output
    workspace_reset: true
  - id: stale
    memory_mode: on
    memory_seed: stale_or_obsolete_fact
    workspace_reset: true
phases:
  - id: seed
    purpose: discover project convention or failure mode
    expected_memory:
      - convention
      - verifier_command
      - known_bad_approach
  - id: recall
    purpose: solve similar non-identical task using prior memory
    success_requires:
      - correct_patch
      - earlier_verifier_use
      - no_repeat_known_bad_approach
  - id: stale
    purpose: verify memory before relying on it
    success_requires:
      - stale_memory_rejected
      - correct_current_workspace_evidence
metrics:
  - reward
  - pass_at_1
  - pass_power_k
  - wall_seconds
  - first_edit_latency_seconds
  - first_verifier_latency_seconds
  - read_count
  - search_count
  - tool_count
  - verifier_count
  - repeated_failure_count
  - memory_items_returned
  - memory_items_injected
  - memory_items_claimed_used
  - memory_evidence_refs
  - stale_memory_rejected
  - reviewer_rescue_required
artifacts:
  - harbor_result_json
  - per_step_reward_json
  - command_transcript_json
  - diff_patch
  - memory_snapshot_before
  - memory_snapshot_after
  - mew_report_json
```

The first task family should stay small:

- Seed: add a feature where the correct source/test path and verifier pattern
  must be discovered by exploration.
- Recall: add a similar feature in a reset workspace where memory should reduce
  search and first-edit latency.
- Stale: inject an obsolete path or verifier command; success requires checking
  the current workspace before reuse.
- Repair-reuse variant: seed a known failed verifier pattern, then test whether
  warm memory avoids the same false-green or timeout shape.

The clean comparison is a 3 x 3 matrix:

```text
conditions: cold, warm, stale
trials:     at least 3 each before tuning; 5 each once stable
agents:     mew memory-off, mew memory-on, Codex reference where practical
```

## Recommended Next Action

Do not adopt a new full benchmark stack for M6.25. Create one Harbor-style
resident-memory task family, using the existing side-project proposal as the
spec, and run it as a local campaign with cold/warm/stale conditions.

Acceptance for the benchmark itself:

- normal coding agents can solve the cold task sometimes;
- warm mew improves at least one of success, first-edit latency, verifier
  latency, or repeated-failure count;
- stale memory can plausibly hurt and is explicitly rejected when correct;
- all scoring comes from verifier artifacts and machine-readable reports;
- no mew-only hidden command such as "call mew memory" is required for success.

After that baseline exists, M6.25 can decide whether to improve mew memory or
whether the task format needs sharpening first.

## Public Sources

- Terminal-Bench GitHub: https://github.com/harbor-framework/terminal-bench
- Harbor task structure: https://www.harborframework.com/docs/tasks
- Harbor multi-step tasks: https://www.harborframework.com/docs/tasks/multi-step
- STATE-Bench Microsoft announcement: https://opensource.microsoft.com/blog/2026/05/19/introducing-state-bench-a-benchmark-for-ai-agent-memory/
- STATE-Bench GitHub: https://github.com/microsoft/STATE-Bench
- MemoryArena project: https://memoryarena.github.io/
- MemoryArena dataset: https://huggingface.co/datasets/ZexueHe/memoryarena
- LongMemEval: https://github.com/xiaowu0162/LongMemEval
- LongMemEval-V2: https://github.com/xiaowu0162/LongMemEval-V2
- SWE-Bench-CL: https://arxiv.org/abs/2507.00014
- SWE-CI GitHub: https://github.com/SKYLENAGE-AI/SWE-CI
- SWE-Chain: https://arxiv.org/abs/2605.14415
- CLIN: https://arxiv.org/abs/2310.10134
- Reflexion: https://arxiv.org/abs/2303.11366
- continuity-benchmarks: https://github.com/Alienfader/continuity-benchmarks
- tau-bench: https://github.com/sierra-research/tau-bench
