# DESIGN 2026-05-05 - M6.23.2 Lane Isolation Substrate

Status: planning

## Decision

Insert **M6.23.2 Lane Isolation Substrate** before the next M6.24 live
Terminal-Bench proof.

The work happens in two steps:

1. Make lanes structurally isolated so a new lane can be added without changing
   unrelated lane behavior.
2. Build `implement_v2` as a separate lane after that boundary exists.

This is a structural pause, not a Terminal-Bench task-specific repair.

## Why

The current implement lane still behaves like a mew-native JSON loop:

```text
THINK JSON -> ACT JSON -> execute one selected action -> observe -> THINK JSON
```

Codex CLI and Claude Code are closer to a provider-native tool loop:

```text
model tool_call/tool_use -> execute tool -> tool_result -> same model loop
```

Trying to retrofit that directly into the current work loop risks three bad
outcomes:

- v1 implement behavior changes while M6.24 evidence is still being collected
- Terminal-Bench repairs become mixed with lane architecture changes
- future lanes inherit implement-lane assumptions because the boundary is not
  explicit

The right move is to isolate lane selection and lane runtime contracts first,
then implement a v2 lane side-by-side.

## Non-Goals

- Do not remove the v1 implement lane in this milestone.
- Do not make `implement_v2` the default.
- Do not add Terminal-Bench-specific shortcuts.
- Do not add provider-specific prompt-cache transport yet.
- Do not introduce a second autonomous planner for memory or deliberation.

## Target Architecture

```text
work session
    |
    v
lane registry
    |
    +-- implement_v1  -> existing mew JSON THINK/ACT adapter
    |
    +-- implement_v2  -> provider-native tool loop runtime
    |
    +-- future lanes  -> research, easy-task, deliberation, build-orchestration
```

Each lane owns its runtime loop, prompt sections, tool policy, transcript
projection, and proof artifacts. Shared services stay below the lane boundary:

```text
lane runtime
    |
    +-- tool specs
    +-- command executor / managed exec
    +-- file read/write/apply-patch execution
    +-- approval policy
    +-- verification / acceptance gates
    +-- journal / metrics / artifacts
```

Shared services may be reused by every lane, but no lane should mutate another
lane's prompts, state schema, tool policy, or transcript format.

## Proposed File Shape

This is a starting shape, not a mandatory final tree:

```text
src/mew/implement_lane/
  __init__.py
  types.py
  lane_registry.py
  dispatcher.py
  transcript.py
  tool_policy.py
  approval.py
  v1_adapter.py
  v2_runtime.py
  providers/
    __init__.py
    codex.py
    anthropic.py
```

Important boundaries:

- `types.py`: lane input/result/transcript/tool-call dataclasses
- `lane_registry.py`: lane lookup and default selection
- `v1_adapter.py`: wraps existing implement behavior without changing it
- `v2_runtime.py`: new provider-native loop, default-off
- `providers/*`: model/provider-specific message and tool-call translation
- shared execution remains in existing mew services unless duplication is
  justified

## Lane Contract V0

Every lane should implement the same small contract:

```text
LaneInput:
  work_session_id
  task_contract
  workspace
  model_config
  lane_config
  persisted_lane_state

LaneResult:
  status
  user_visible_summary
  proof_artifacts
  next_reentry_hint
  updated_lane_state
  metrics
```

The contract must make lane artifacts comparable without forcing every lane to
share the same internal loop.

## Implement V2 Direction

`implement_v2` should be designed like a real coding shell lane:

- provider-native tool calls when the provider supports them
- stable tool-call ids and paired tool results
- read/search tools first-class, not parsed out of prose
- write/edit/apply-patch tools approval-gated
- managed command execution returns nonterminal/running/finalized states
- transcript replay can reconstruct why the model chose each next action
- prompt sections are assembled through the prompt section registry, not by
  growing one large inline prompt

## Phases

### Phase 1 - Lane Selection Boundary

- Add a lane registry and explicit lane selection field.
- Keep v1 as the default.
- Route current implement work through a v1 adapter with no behavior change.

Evidence:

- existing focused implement-lane tests still pass
- a no-op v1 lane run produces the same high-level artifacts as before

### Phase 2 - Shared Lane Types and Transcript Skeleton

- Add lane input/result types.
- Add transcript event types for model message, tool call, tool result, approval,
  verifier, and finish.
- Ensure transcripts are lane-namespaced.

Evidence:

- unit tests for transcript serialization
- no collision between v1 and a placeholder v2 transcript namespace

### Phase 3 - Read-Only `implement_v2` Spike

- Add a default-off v2 lane that can call read/search/probe tools and feed tool
  results back into the same model loop.
- No writes yet.

Evidence:

- v2 can inspect a workspace and produce a plan/diagnosis
- v1 still works as default

### Phase 4 - Managed Command Tool

- Add managed command execution to v2 through the shared execution substrate.
- Preserve nonterminal/running/finalized state and output paths.

Evidence:

- a long-ish command can be started, polled, and finalized without blocking the
  model loop forever

### Phase 5 - Write/Edit/Patch Tools

- Add write/edit/apply-patch tools behind approval and dry-run surfaces.
- Reuse existing verification and acceptance gates.

Evidence:

- v2 can make a small approved edit in a fixture repo
- rejected edits remain replayable and repairable

### Phase 6 - M6.24 Reentry A/B Gate

- Run a small A/B proof that v1 and v2 can both run from the same mew checkout
  without artifact collision.
- Only then resume M6.24 live proof work with an explicit lane choice.

Evidence:

- v1 baseline remains valid
- v2 produces separate artifacts and metrics
- M6.24 status clearly states which lane was used

## Done When

- v1 remains the default and passes focused regression.
- v1 and v2 artifacts are lane-namespaced and do not collide.
- adding a placeholder lane does not require editing v1 runtime internals.
- `implement_v2` can complete a read-only model/tool/result loop.
- write/edit/apply-patch support is designed and gated, even if default-off.
- M6.24 can resume with explicit `implement_v1` or `implement_v2` selection.

## Drift Guard

If a future context resumes M6.24 and starts new live Terminal-Bench proof while
this boundary is missing, treat that as drift. Re-read this document,
`ROADMAP.md`, and `ROADMAP_STATUS.md`, then either close M6.23.2 or explicitly
defer it with a written decision.
