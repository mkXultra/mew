# M6.25 Resident Advantage Plan

Date: 2026-05-20 JST

## Goal

M6.25 proves that mew is not merely a Codex-like terminal agent, but a better
resident coding body because it can preserve context, reuse repair knowledge,
survive reentry, and reduce repeated-work cost.

M6.25 must preserve the M6.24 baseline. It must not reopen broad
Terminal-Bench proof collection unless a specific M6.25 experiment needs a
named regression check.

## Non-Goals

- Do not resume M6.24 proof_5 spending by reflex.
- Do not add broad memory into the live model path before measuring a bounded
  read-only variant.
- Do not make provider cache transport change default scoring behavior.
- Do not claim resident advantage from prompt tuning alone.

## Phase Plan

### Phase 0 - Baseline And Guard

Purpose: keep M6.24 closed while M6.25 experiments begin.

Work:

- Treat `docs/M6_24_STAGED_CLOSE_REPORT_2026-05-20.md` as the active baseline.
- Keep `implement_v2 / codex_hot_path` as the non-cache scoring path.
- Add a small M6.25 experiment ledger before changing live behavior.
- Define the three evidence axes for every experiment:
  - quality: pass/fail or verifier result
  - resident advantage: what persisted/reused/recovered
  - cost/latency: turns, wall time, first edit, prompt section metrics, token/cost
    when available

Close gate:

- M6.25 ledger exists.
- First experiment is selected with a cold-vs-resident comparison shape.
- No M6.24 proof_5 is selected as the next action.

### Phase 1 - Memory-Light Reentry Advantage

Purpose: prove that mew can resume with better state than a cold agent without
polluting the model hot path.

Work:

- Use existing context save/load and decision-memory surfaces.
- Compare cold run vs resident reentry on one small coding/recovery task.
- Inject only lane-local reentry hints and explicit prior repair decisions.
- Record whether the resident run avoids rediscovering known failures.

Candidate evidence:

- `reshard-c4-data`: finish-verifier temp cleanup repair should be remembered as
  a generic safety rule, not rediscovered.
- `pypi-server`: managed-service closeout behavior should be remembered.
- `merge-diff-arc-agi-task`: finish-verifier cwd propagation should be
  remembered.

Close gate:

- At least one cold-vs-resident comparison is recorded.
- Resident path either improves latency/turns or avoids a known repeated failure.
- Any score regression is explicitly recorded.

### Phase 2 - Bounded Read-Only Memory Summary

Purpose: add `implement_v2_v1` memory summary only if it is bounded, inspectable,
and measurable.

Work:

- Add a prompt-section memory summary that is read-only and size-capped.
- Source it from typed project memory / gap ledger entries.
- Record section id, hash, stability, cache policy, chars, and selected memory refs.
- Keep full memory files out of provider-visible input.

Close gate:

- Focused tests prove the memory summary is bounded and private-memory safe.
- A/B run shows the memory summary changes useful next action or repair reuse
  without changing task semantics.

### Phase 3 - MemoryExploreProvider V2 Boundary

Purpose: prepare read-only memory exploration as a provider/tool surface without
creating a second planner.

Work:

- Keep `MemoryExploreProvider` read-only.
- Expose only search/query results and compact refs.
- Prevent memory explorer from writing, selecting tasks, or creating autonomous
  subplans.

Close gate:

- Tool/provider contract is replayable.
- One experiment shows memory exploration can retrieve a relevant prior repair
  without adding live-loop drift.

### Phase 4 - Provider Cache Transport

Purpose: connect prompt-section cache metadata to provider-specific cache
transport behind a feature flag.

Work:

- Keep provider-neutral `PromptSection` ids, hashes, stability, and cache policy
  as source of truth.
- Add provider adapters behind default-off flags.
- Record cache-on/cache-off usage, latency, token/cost, prompt-section hashes,
  and score delta.

Close gate:

- Default non-cache scoring path is unchanged.
- Cache-enabled and non-cache prompt semantics are equivalent by replay or
  request artifact comparison.
- At least one representative coding loop records cache-on/cache-off metrics.

### Phase 5 - Resident Advantage Report

Purpose: answer whether mew is now preferable to inhabit.

Work:

- Summarize where mew equals Codex, where resident state wins, and where it still
  loses.
- Include at least three previously failed or below-target tasks improved
  through memory/diagnosis/reentry rather than one-off supervisor rescue.
- Include future task classes that should move outside Terminal-Bench.

Close gate:

- M6.25 report exists.
- M6.24 baseline remains protected.
- The report gives a clear answer to: "Would I rather be inside mew than Codex
  CLI for coding work?"

## First Next Action

Create the M6.25 experiment ledger and select Phase 1 candidate #1:
`reshard-c4-data` resident repair-reuse comparison.

Do not run proof_5. The first experiment should be a bounded cold-vs-resident
comparison that measures whether prior repair knowledge changes reentry and
next-action quality.
