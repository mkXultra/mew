# Side Project: Harbor Resident Memory Benchmark

Date: 2026-04-30
Status: side-project proposal
Owner: side-project operator

This document is intentionally independent from `ROADMAP.md` and
`ROADMAP_STATUS.md`.

Do not update the main roadmap for this work unless the user explicitly asks.
The purpose is to prepare a side-project benchmark that can later tell whether
mew's resident memory improves implementation-lane performance.

## Purpose

Current Terminal-Bench / Harbor tasks measure coding ability, but they do not
measure whether a resident agent benefits from durable memory across sessions.

The side project should add one or more Harbor tasks that can answer:

- Does memory reduce repeated exploration?
- Does memory reduce first-edit latency?
- Does memory improve pass rate on repeated task shapes?
- Can the agent reject stale or misleading memory?
- Can the benchmark compare memory-on and memory-off runs cleanly?

## Non-Goals

- Do not change mew M6 milestone gates.
- Do not optimize mew memory before a baseline exists.
- Do not create a mew-only toy task that simply checks whether `mew memory`
  was called.
- Do not grant hidden write authority to helper agents.
- Do not use this benchmark as M6.24 parity evidence until it has a stable
  task spec and baseline.

## Task Shape

Use a task family with at least three phases.

### Phase A: Seed

The agent solves an initial development task where the useful information is
discoverable only through normal exploration.

Examples:

- discover the source/test file pair for a small feature
- discover a project-local convention
- discover that a tempting approach is rejected by tests
- discover a verifier quirk or required command shape

The run should produce a durable fact that would be useful later.

### Phase B: Recall

The agent receives a similar but not identical task in a fresh session or fresh
workspace state.

Memory should help it:

- choose the correct source/test pair faster
- avoid repeating a known bad approach
- run the right verifier earlier
- preserve the project-local convention without reviewer steering

### Phase C: Stale Or Misleading Memory

The task includes one stale, misleading, or partially obsolete memory entry.

The correct behavior is not blind reuse. The agent should verify the memory
against the current workspace before relying on it.

## Measurement

Every task run should emit a machine-readable report with:

- `task_id`
- `phase`
- `memory_mode`: `on`, `off`, or `stale`
- `success`
- `score`
- `first_edit_latency_seconds`
- `read_count`
- `search_count`
- `tool_count`
- `verifier_count`
- `memory_items_returned`
- `memory_items_injected`
- `memory_items_claimed_used`
- `stale_memory_rejected`
- `reviewer_rescue_required`
- `notes`

The important comparison is not absolute score only. The benchmark should
compare:

```text
memory_on  vs  memory_off
memory_on  vs  stale_memory
first run  vs  repeated shape
```

## Baseline Protocol

Before improving mew memory, run the benchmark in this order:

1. `memory_off` baseline
2. `memory_on` current mew baseline
3. `stale_memory` current mew baseline

Only after those baselines exist should mew memory behavior be changed.

## Good Task Criteria

A good resident-memory task:

- is solvable by a normal coding agent without memory
- becomes cheaper or more reliable when memory is useful
- penalizes blind memory reuse
- has deterministic verifier output
- does not require external network access
- does not depend on mew-specific internals
- can be run by Harbor in the same style as Terminal-Bench tasks

## Bad Task Criteria

Avoid tasks where:

- the only correct action is "call mew memory"
- the task leaks the answer directly in the prompt
- the second run is an exact duplicate of the first
- success depends on wall-clock waiting
- stale memory cannot actually cause a plausible wrong action
- scoring is based on prose rather than artifacts or tests

## Suggested Initial Task Family

Use a tiny Python package with a hidden local convention.

Seed task:

- Add a small feature.
- The agent must discover that implementation lives in `src/` but behavior is
  verified through a golden-file test under `tests/golden/`.
- A naive direct unit test is insufficient.

Recall task:

- Add a second feature with the same convention.
- Memory should point to the source/test pair and golden verifier pattern.

Stale task:

- Include a memory entry pointing to the old golden path, but move the actual
  verifier to a new path.
- The agent should inspect before trusting the memory.

## Side-Project Operator Flow

1. Create the Harbor task outside the mew main roadmap flow.
2. Keep changes isolated in the side-project directory or branch.
3. Run a small local proof that the task can pass and fail deterministically.
4. Record baseline results for memory-off and memory-on.
5. Report only if:
   - the task spec is ambiguous,
   - the benchmark cannot produce stable scores,
   - mew core changes appear necessary,
   - or baseline results are ready for review.

## Output Artifacts

Recommended artifacts:

- task spec markdown
- task fixture directory
- verifier script
- baseline result JSONL
- short findings report

Suggested report fields:

```json
{
  "benchmark": "resident-memory",
  "task_family": "golden-convention-recall",
  "memory_off_score": null,
  "memory_on_score": null,
  "stale_memory_score": null,
  "first_edit_latency_delta_seconds": null,
  "search_count_delta": null,
  "stale_memory_rejected": null,
  "ready_for_mew_improvement": false
}
```

## Decision Rule

If the benchmark cannot distinguish memory-on from memory-off behavior, fix the
benchmark before changing mew.

If memory-on improves speed but not correctness, treat it as an ergonomics
signal, not product proof.

If memory-on improves correctness and stale-memory rejection remains green,
then memory effectiveness becomes a strong candidate for a future mew
improvement track.
