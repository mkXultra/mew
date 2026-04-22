# Mew Loop Stabilization Design (2026-04-22)

## Executive Summary

Mew's unstable point is no longer exploration. It is the gap between `plan_item_observations[0].edit_ready` and a reviewer-visible dry-run patch. The current loop already knows when exact paired source/test windows are cached, and it already has strict write tools, approval gates, and durable resume state. What it does not have is a first-class drafting contract.

The next architecture should insert one mew-specific layer between cached windows and the existing dry-run write/apply flow:

1. A persisted `WorkTodo` that owns exactly one in-progress drafting frontier.
2. A `PatchDraftCompiler` that turns a tiny model proposal into either a validated patch artifact or one exact blocker.
3. A drafting-specific recovery lane that resumes from the same cached windows instead of collapsing to generic `replan`.

This borrows the right parts of both references without copying them wholesale:

- From Claude Code: executor discipline, explicit lifecycle states, fail-closed concurrency defaults, and a session-owned current task ledger.
- From Codex: patch artifact first, deterministic validator second, isolated review contract third.
- From mew itself: exact cached windows, paired `src/mew/**` + `tests/**` editing discipline, dry-run/approval/apply gates, and durable resume/follow-status surfaces.

The opinionated implementation order is:

1. Freeze prompt churn.
2. Land the `WorkTodo` and patch compiler contracts.
3. Add replay fixtures for `#399` and `#401`.
4. Only then rewire the write-ready fast path to use the new contract.

## Problem Statement

Today the work loop has a clear pre-draft observation model but not a clear draft execution model.

- `src/mew/work_session.py` can already prove that paired target paths are fully cached and mark the first plan item `edit_ready`.
- `src/mew/work_loop.py` can already narrow the prompt to a write-ready fast path and extend the THINK timeout to `90s`.
- `src/mew/write_tools.py` already enforces exact old-text matching, ambiguous-match rejection, and atomic same-file hunk application.
- `src/mew/commands.py` and `build_work_session_resume()` already provide approval, apply, verify, and recovery surfaces.

The unstable step is still one large model turn that must invent a valid dry-run tool batch from scratch. That causes both known failure buckets:

- `#399`: exact cached windows exist, but no safe dry-run patch is produced. The model can still return `wait`, malformed JSON, or another read/search action because `edit_ready` is only advisory.
- `#401`: exact cached windows exist, but the draft turn times out before any patch artifact exists. Recovery then degrades to generic `replan`, which loses the fact that the loop had already reached a drafting-ready state.

There are four structural causes behind those failures:

1. `edit_ready` is an observation, not a durable drafting state.
2. The write-ready fast path is still prompt-shaped, not compiler-shaped.
3. Model-turn recovery is generic, while tool recovery is typed and explicit.
4. There is no replayable patch/blocker artifact to inspect after failure.

The design goal is not to make the prompt slightly smarter. It is to remove this instability from the prompt entirely.

## Design Goals

1. Make `edit_ready` executable. Once paired exact cached windows are proven, the next step must be "draft patch or emit exact blocker," not "plan again."
2. Preserve mew's current strengths. The new loop must keep exact cached windows, paired source/test discipline, dry-run approval, deterministic write tools, and durable resume/follow-status behavior.
3. Prefer contracts over prose. The main stabilization work should live in runtime objects, typed state, validators, and regression fixtures, not in a longer prompt.
4. Make `#399` and `#401` replayable offline. A live failure should produce enough structured state to reproduce the break without a full resident session.
5. Keep writes conservative. Serial write/apply/verify semantics stay strict; concurrency expansion is not a phase-1 requirement.
6. Fail with exact reasons. The loop should surface classified blockers such as `stale_cached_window_text` or `ambiguous_old_text_match`, not generic "model failed" or "replan."
7. Keep the architecture mew-specific. Do not import Claude Code's subagent stack or Codex's patch shell compatibility surface. Reuse mew's own approval, resume, and pairing rules.
8. Make the drafting contract prompt-cache-friendly. The stable instructions and schema should remain fixed across retries and nearby tasks, while only the `WorkTodo` and cached-window payload vary.

## Proposed Architecture

### 1. Promote write-ready into a persisted `WorkTodo`

When `build_work_session_resume()` proves that the first actionable plan item is `edit_ready`, the session should open or update one `WorkTodo` record. This is a session-local drafting frontier, not a replacement for global `tasks.py` and not derived only from model prose.

`WorkTodo` owns:

- the current paired target paths
- exact cached window refs
- the requested exact window, if one exists
- the expected verifier
- the current drafting status
- the current blocker or validated patch artifact
- bounded attempt counters

This is the Claude Code lesson adapted to mew: do not make the loop rediscover "what is the current draft step?" from prompt history.

### 2. Replace the write-ready fast path with a patch draft lane

The write-ready path should stop asking the model for a full next action and stop asking it to invent tool-call JSON. Once a `WorkTodo` exists, the model gets one tiny contract:

- return a `patch_proposal`, or
- return a classified `patch_blocker`

The input to that draft lane is deliberately small:

- `WorkTodo`
- exact cached source/test window texts
- write policy
- verifier hint
- optionally the most recent reviewer findings

The output is not a tool batch. It is an intermediate patch artifact proposal that must pass validation before any write tool call exists.

This is the Codex lesson adapted to mew: patch text is a first-class artifact, not an implied side effect of a planning turn.

### 2.5. Make the draft lane prompt-cache-aware by construction

The tiny drafting contract should also be intentionally shaped for prompt caching.

That means splitting the draft request into:

- a stable prefix:
  - fixed instructions
  - frozen patch schema
  - blocker taxonomy summary
  - stable policy clauses
- a dynamic suffix:
  - `WorkTodo`
  - exact cached window texts or refs
  - verifier hint
  - narrow reviewer findings if present

Rules:

- retries should reuse the same stable prefix whenever possible
- the contract should be versioned so cache-affecting wording changes are deliberate
- recovery retries should prefer "same prefix, smaller suffix" instead of rewriting the whole prompt
- prompt budget tests should distinguish stable vs dynamic segments, not only total chars

This does not require provider-specific caching logic in Phase 0-4. It only requires the architecture to stop rebuilding the entire drafting prompt shape on every attempt.

### 3. Add a deterministic `PatchDraftCompiler`

`PatchDraftCompiler` should be a pure module, likely `src/mew/patch_draft.py`, with no filesystem mutation and no approval logic. Its job is to translate a tiny model proposal into:

- `PatchDraft`, or
- `PatchBlocker`

Validator responsibilities:

- verify every edit path is allowed and matches the active `WorkTodo`
- verify every `old` string exists in the cached window text
- verify the cached window content hash still matches the live file
- verify same-file hunks are disjoint and ordered
- reject no-op edits
- enforce mew's existing paired `src/mew/**` + `tests/**` code-write policy
- produce the unified diff and exact tool translation that preview/apply will consume

The important design point is that dry-run preview, approval, apply, verify, replay, and review all inspect the same validated artifact.

### 4. Keep mew's existing write surfaces and approval gates

This design does not replace `write_tools.py` or the approval flow in `commands.py`.

Instead:

- `PatchDraftCompiler` produces a validated draft artifact.
- That artifact is translated into existing dry-run `edit_file` / `edit_file_hunks` calls.
- The diff shown to the user is the same diff the validator approved.
- Apply and verify continue to use mew's current gates.

This preserves one of mew's strongest properties: the loop already has a safe write boundary. The missing piece is upstream.

### 5. Add a drafting-specific review lane

Review should become an explicit phase after draft validation and before apply. The reviewer input should be isolated:

- validated diff
- cached windows used to justify the diff
- verifier hint
- optional narrow task summary

Reviewer output should be structured:

- `accepted`
- or findings with `severity`, `path`, `reason`, `suggested_fix`

This is Codex-style review discipline, but it should be introduced only after the patch artifact exists. Until then, there is nothing stable to review.

### 6. Tighten runtime discipline around terminal states

Mew should adopt Claude Code style runtime discipline where it helps loop stability:

- default tools to non-concurrent until proven safe
- distinguish `queued`, `executing`, `completed`, `cancelled`, and `yielded`
- never leave a started tool or draft attempt without a terminal record
- keep separate cancellation domains for read batches, write/apply batches, and verify batches

This should be phased in after the draft lane lands. It is valuable, but it is not the first blocker behind `#399` and `#401`.

### 7. Reserve a read-only `MemoryExploreProvider`, not a full agent yet

M6.9 memory work should eventually be callable through the same structural explore boundary, but it should not become a free-standing autonomous agent before the draft lane is stable.

The right shape is:

- an optional read-only `MemoryExploreProvider`
- invoked only from `exploring`
- allowed to read typed memory, durable memory indexes, and symbol/file-pair memory
- required to emit the same handoff shape as filesystem exploration:
  - `target_paths`
  - `cached_window_refs`
  - `candidate_edit_paths`
  - `exact_blockers`

This keeps memory-assisted exploration structurally aligned with filesystem exploration. The loop still sees one explore contract and one drafting contract, instead of mixing a second partially autonomous planner into the middle.

This also leaves room for a future `memory explore agent` if needed, but only after:

- `WorkTodo` exists
- `PatchDraftCompiler` exists
- drafting-specific recovery is stable
- executor lifecycle states are explicit enough to supervise another read-only worker safely

Until then, memory exploration should be modeled as a provider behind the explore phase, not a new autonomous surface.
This provider is explicitly deferred protocol work. It is not a prerequisite for Phase 5 review or Phase 6 executor tightening.

### 8. If memory exploration later becomes an agent, freeze the protocol first

The main concern with a future `memory explore agent` is not capability. It is debuggability. If it is introduced as a second planner with a loosely specified prompt, loop failures will become harder to localize than they are today.

To avoid that, the protocol must be fixed *before* an agent backend exists.

Required protocol properties:

- one request in, one handoff artifact out
- read-only by construction
- no nested planning authority
- no direct write, approval, verify, or task-selection powers
- bounded runtime and explicit terminal states
- replayable offline from saved request/response bundles

The provider interface should therefore be defined as a stable contract that can be backed by:

- an in-process memory query implementation
- or a future read-only memory explorer worker/agent

without changing the rest of the loop.

#### Provisional `MemoryExploreRequest` fields

The request field list below is provisional until two things are stable:

- M6.9 Phase 1 memory taxonomy closes
- filesystem exploration has its own explicit handoff artifact, rather than today's implicit `recent_read_file_windows` plus resume observations

The non-goals, terminal states, and replay bundle format can be frozen now. The exact request/result fields should remain provisional until those upstream contracts stop moving.

The request should contain only what a read-only explorer needs:

- active task id
- current `WorkTodo` summary if one exists
- target topic or question
- allowed memory kinds / indexes
- current filesystem target paths
- time budget
- result budget
- trace ids

#### Provisional `MemoryExploreResult` fields

This result shape is also provisional for the same reason: it should eventually match the frozen filesystem explore handoff contract, not guess ahead of it.

The result must use the same handoff shape as filesystem exploration:

- `target_paths`
- `cached_window_refs`
- `candidate_edit_paths`
- `exact_blockers`

and may additionally include:

- `memory_refs`
- `reason_for_use`
- `provider_runtime_mode`
- `provider_latency_ms`
- `provider_stop_reason`

#### Terminal states

Even for a future agent-backed provider, results must end in one of:

- `completed`
- `timed_out`
- `cancelled`
- `failed`
- `blocked`

No silent partial completion is allowed. If the provider times out or returns malformed output, the main loop should record a classified blocker and continue to own recovery.

#### Replay bundle requirements

Every provider invocation should be reproducible from a bundle such as:

```text
.mew/replays/memory-explore/<date>/session-<id>/attempt-<n>/
  request.json
  result.json
  memory_snapshot.json
  selected_refs.json
  notes.txt
```

This lets the future agent backend be debugged without re-running the whole resident loop.

#### Non-goals for the future agent backend

Even if the provider is later implemented as an agent, it should still not:

- choose the next milestone or task
- open write tools
- draft patches
- decide approval/apply/verify
- rewrite the `WorkTodo`

The main loop remains the sole owner of those responsibilities.

### End-to-end flow

```text
explore/read
  -> exact cached windows proven
  -> WorkTodo(status=drafting)
  -> model emits PatchProposal or PatchBlocker
  -> PatchDraftCompiler validates
     -> PatchDraft -> dry-run preview -> review -> approval -> apply -> verify -> complete
     -> PatchBlocker -> blocked_on_patch with exact recovery action
```

## Runtime State Model

### Session phase states

The session should expose one explicit loop phase, separate from tool-call status.

Canonical source of truth invariant:

- `active_work_todo.status` is the canonical runtime state once a draft frontier exists.
- `session phase` is always derived from `active_work_todo.status` plus pre-draft loop state.
- `session phase` must never be stored or updated independently when an `active_work_todo` exists.

Derived session phases:

- `exploring`
- `drafting`
- `blocked_on_patch`
- `awaiting_review`
- `awaiting_approval`
- `applying`
- `verifying`
- `completed`
- `interrupted`

Derivation rules:

- no active todo and no draft-ready frontier: `exploring`
- active todo present: `session phase = active_work_todo.status`
- producer interrupted or runtime tombstone present: `interrupted`

Current mew phases such as planning/idle/awaiting approval can remain implementation detail inside the executor, but they do not become a second source of truth.

### Core runtime objects

#### `WorkTodo`

```json
{
  "id": "todo-17",
  "status": "drafting|blocked_on_patch|awaiting_review|awaiting_approval|applying|verifying|completed",
  "source": {
    "plan_item": "Draft one paired dry-run edit batch for src/mew/work_loop.py and tests/test_work_session.py",
    "target_paths": ["src/mew/work_loop.py", "tests/test_work_session.py"],
    "verify_command": "uv run python -m unittest tests.test_work_session"
  },
  "cached_window_refs": [
    {
      "path": "src/mew/work_loop.py",
      "line_start": 1386,
      "line_end": 1400,
      "window_sha256": "...",
      "file_sha256": "..."
    }
  ],
  "attempts": {
    "draft": 0,
    "review": 0
  },
  "patch_draft_id": "",
  "blocker": {},
  "created_at": "",
  "updated_at": ""
}
```

#### `PatchDraft`

```json
{
  "id": "draft-3",
  "todo_id": "todo-17",
  "status": "validated|review_rejected|approved|applied|verified",
  "files": [
    {
      "path": "src/mew/work_loop.py",
      "kind": "edit_file_hunks",
      "edits": [{"old": "...", "new": "..."}],
      "window_sha256s": ["..."],
      "pre_file_sha256": "...",
      "post_file_sha256": "..."
    }
  ],
  "unified_diff": "...",
  "validator_version": 1,
  "created_at": ""
}
```

#### `PatchBlocker`

```json
{
  "todo_id": "todo-17",
  "code": "stale_cached_window_text",
  "path": "src/mew/work_loop.py",
  "line_start": 1386,
  "line_end": 1400,
  "detail": "live file hash differs from cached window hash",
  "recovery_action": "refresh_cached_window",
  "created_at": ""
}
```

### Required invariants

1. Exactly one `WorkTodo` may be active in drafting/apply/verify states at a time.
2. `WorkTodo.status=drafting` requires exact untruncated cached window refs for every target path.
3. When an active todo exists, `session phase` must be derived directly from `WorkTodo.status`; no independent phase mutation is allowed.
4. `PatchDraft` is immutable once shown to the reviewer or user; later phases can only annotate status.
5. Apply must consume the same `PatchDraft` that dry-run preview and review consumed.
6. A generic `replan` recovery item is forbidden while an active `WorkTodo` exists unless the blocker explicitly says the draft lane is invalidated.
7. Every started tool call, model turn, and draft attempt must end in a terminal status with a reason code.

## Patch Draft Contract

### Draft request

The write-ready draft model call should be reduced to one narrow schema:

```json
{
  "kind": "patch_proposal|patch_blocker",
  "summary": "short reason",
  "files": [
    {
      "path": "src/mew/work_loop.py",
      "edits": [
        {"old": "exact old text", "new": "replacement text"}
      ]
    }
  ],
  "code": "blocker code when kind=patch_blocker",
  "detail": "why drafting cannot proceed"
}
```

Rules:

- no read/search/tool actions
- no new target paths
- no shell commands
- no approval decisions
- same-file multiple hunks must be expressed in one `files[i].edits` array
- draft scope must stay inside the `WorkTodo.target_paths`

### Validator output

The compiler returns exactly one of:

- `PatchDraft`
- `PatchBlocker`

Validator checks:

1. Path is one of the active target paths.
2. Path is allowed by current write roots.
3. Each `old` string appears in cached text.
4. Each `old` string still matches the live file hash context.
5. Same-file hunks do not overlap.
6. The resulting file actually changes.
7. Mew's paired code-write policy is satisfied.

### Blocker taxonomy

These codes should be frozen early and used consistently in runtime state, follow-status, and tests:

- `missing_exact_cached_window_texts`
- `cached_window_text_truncated`
- `stale_cached_window_text`
- `old_text_not_found`
- `ambiguous_old_text_match`
- `overlapping_hunks`
- `no_material_change`
- `unpaired_source_edit_blocked`
- `write_policy_violation`
- `model_returned_non_schema`
- `model_returned_refusal`
- `review_rejected`

This taxonomy matters because mew needs exact recovery choices, not one generic fallback.

### Review contract

The review phase should consume only:

- `PatchDraft.unified_diff`
- the cached windows that justified it
- verifier hint
- optional previous review findings

Reviewer output:

```json
{
  "status": "accepted|rejected",
  "findings": [
    {
      "severity": "high|medium|low",
      "path": "tests/test_work_session.py",
      "reason": "missing paired assertion for new timeout recovery path",
      "suggested_fix": "add a replay assertion for resume_draft_from_cached_windows"
    }
  ]
}
```

## Recovery Contract

Recovery should become contract-driven and todo-aware.

### Recovery rules

1. If a draft attempt times out before returning schema-valid output:
   - keep the same `WorkTodo`
   - mark the attempt `timed_out`
   - increment `attempts.draft`
   - surface `resume_draft_from_cached_windows`
   - allow one bounded retry with the same cached windows and the same tiny draft contract after re-verifying hashes

2. If the model returns malformed or non-schema output while exact windows are still valid:
   - create `PatchBlocker(code=model_returned_non_schema)`
   - do not reopen broad exploration
   - surface the blocker in resume/follow-status

3. If the validator detects stale hashes:
   - create `PatchBlocker(code=stale_cached_window_text)`
   - recovery must be `refresh_cached_window` for the affected path/span only
   - after refresh, reuse the same `WorkTodo`

4. If the validator detects missing pairing:
   - create `PatchBlocker(code=unpaired_source_edit_blocked)`
   - recovery must be "draft the missing paired tests edit," not apply source-only

5. If review rejects the draft:
   - keep the same `WorkTodo`
   - attach structured findings
   - next action is `revise_patch_from_review_findings`

6. If a dry-run preview exists and approval/apply/verify is interrupted:
   - keep using mew's existing `retry_dry_run_write`, `retry_apply_write`, `verify_completed_write`, and `retry_verification`
   - do not re-enter the draft compiler unless the artifact itself is invalidated

### Recovery action vocabulary

These recovery actions should replace generic replan in draft-related cases:

- `resume_draft_from_cached_windows`
- `refresh_cached_window`
- `revise_patch_from_review_findings`
- `retry_dry_run_preview`
- `retry_apply_validated_patch`
- `verify_completed_patch`

`replan` remains valid only for genuinely pre-draft failures.

### Terminal-state rule

On interrupt, timeout, fallback, or producer death:

- tool calls move to a terminal status
- draft attempts move to a terminal status
- untouched siblings become `cancelled` or `not_run`
- follow-status and resume must point at the same terminal reason code

The loop should never require transcript archaeology to determine whether drafting had already started.

## Replay / Regression Strategy

The architecture is not acceptable unless failures can be replayed without a live resident loop.

### Fixture layout

Create scenario directories under:

```text
tests/fixtures/work_loop/patch_draft/
tests/fixtures/work_loop/recovery/
tests/fixtures/work_loop/follow_status/
```

Each scenario should include only the minimum state required to reproduce a failure:

```text
session.json
task.json
cached_windows.json
disk/
model_output.json
expected_patch.diff
expected_blocker.json
expected_recovery.json
expected_follow_status.txt
```

### Required harnesses

1. `PatchDraftCompiler` replay harness
   - loads `WorkTodo`, cached windows, disk state, and model proposal
   - returns a golden diff or blocker
   - requires no live model and no resident session

2. Draft timeout replay harness
   - starts from a write-ready `WorkTodo`
   - forces timeout in guarded and streaming modes
   - asserts the same todo survives and recovery becomes `resume_draft_from_cached_windows`

3. Resume/follow-status replay harness
   - loads interrupted session state plus snapshot data
   - asserts resume JSON and follow-status text expose the same blocker and next action

4. Review replay harness
   - feeds a validated draft and synthetic findings
   - asserts the todo moves to `review_rejected` and stays patch-scoped

### Live failure bundles

Every draft timeout or validator blocker should produce a reproducible bundle under a stable location such as:

```text
.mew/replays/work-loop/<date>/session-<id>/todo-<id>/attempt-<n>/
```

Bundle contents:

- `resume.json`
- `work_todo.json`
- `draft_request.json`
- `model_output.json` if any
- `validator_result.json`
- `follow_status.json`
- `disk_manifest.json`
- `notes.txt` with absolute file paths and hashes

This is the main debuggability improvement. A broken loop should become a local fixture, not a vague transcript anecdote.

## Test Matrix

| Area | Scenario | What it proves |
| --- | --- | --- |
| Draft compiler | Paired source/test happy path | Exact cached windows compile to one validated diff with no extra reads |
| Draft compiler | Same-file multi-hunk edit | Same-file edits collapse into one artifact and preserve ordering |
| Draft compiler | `old_text_not_found` | Missing exact text fails as blocker, not re-exploration |
| Draft compiler | `ambiguous_old_text_match` | Duplicate matches fail deterministically before preview |
| Draft compiler | `stale_cached_window_text` | Live file drift invalidates cached windows explicitly |
| Draft compiler | `unpaired_source_edit_blocked` | Existing mew paired-edit policy remains enforced |
| Work loop | `#399` model returns `wait` with exact cached windows | The loop produces `model_returned_non_schema` or exact blocker, not a same-surface reread |
| Work loop | `#399` malformed JSON in write-ready mode | Draft contract failure is isolated and classified |
| Work loop | `#401` non-streaming timeout | Recovery preserves `WorkTodo` and suggests `resume_draft_from_cached_windows` |
| Work loop | `#401` streaming timeout | Same recovery semantics hold even when the fork guard is not active |
| Work loop | child-crash fallback during draft | Degraded mode is recorded and does not erase draft state |
| Review | reviewer rejects validated diff | Findings stay attached to the same todo and drive revision |
| Approval/apply | validated diff -> dry-run -> approval -> apply -> verify | One artifact flows through the whole write path |
| Resume/follow | producer dies mid-draft | Resume JSON and follow-status surface the same blocker/action |
| Resume/follow | session newer than snapshot | Follow-status prefers the newer session state without losing latest blocker metrics |

The first two regression fixtures that must exist before prompt changes are:

- `tests/fixtures/work_loop/recovery/399_exact_windows_no_patch/`
- `tests/fixtures/work_loop/recovery/401_exact_windows_timeout_before_draft/`

## Observability / Debug Surface

### Session and resume fields

Extend session state and `build_work_session_resume()` with draft-specific fields:

- `active_work_todo`
- `draft_phase`
- `draft_attempts`
- `latest_patch_blocker`
- `latest_patch_draft_id`
- `cached_window_ref_count`
- `cached_window_hashes`
- `draft_runtime_mode` (`guarded|streaming|fallback_unguarded`)
- `latest_review_status`
- `draft_prompt_contract_version`
- `draft_prompt_static_chars`
- `draft_prompt_dynamic_chars`
- `draft_retry_same_prefix`

### Follow-status additions

`work --follow-status` should expose draft-specific details directly:

- `phase: drafting|blocked_on_patch|awaiting_review`
- `todo_id`
- `draft_attempt`
- `blocker_code`
- `blocker_path`
- `draft_runtime_mode`
- `validator_version`
- `latest_model_failure` metrics
- `next_recovery_action`

If a draft failure is the reason the loop stopped, follow-status should not only say "request timed out." It should say "draft timeout while exact cached windows were active for todo-17; recovery=resume_draft_from_cached_windows."

### Traceability requirements

Every draft attempt should carry stable identifiers:

- `todo_id`
- `draft_id`
- `model_turn_id`
- `tool_call_ids`
- `review_id`

That gives one linear chain from cached windows to applied diff.

### What to log and freeze

Freeze these reason codes early and log them everywhere:

- blocker code
- recovery action
- runtime mode
- validator version
- attempt count
- prompt contract version
- static vs dynamic prompt char counts

Do not rely on freeform summaries for machine diagnosis.

## Implementation Phases

### Phase 0: Freeze and instrument

Scope:

- freeze further write-ready prompt tweaking
- freeze a versioned tiny drafting prompt envelope with stable-prefix / dynamic-suffix separation
- add session/resume placeholders for `WorkTodo` and draft metrics
- define blocker and recovery enums

What this phase proves:

- new failures can at least be classified the same way everywhere
- prompt-cache-sensitive changes become explicit contract changes instead of incidental wording churn
- later implementation will not chase moving prompt wording

### Phase 1: Persist `WorkTodo`

Scope:

- add `WorkTodo` storage and transitions in `src/mew/work_session.py`
- bind `edit_ready` observations to `WorkTodo` creation/update
- include cached window hashes and verifier hint

What this phase proves:

- the drafting frontier survives resume/restart
- `edit_ready` becomes durable state instead of a prompt-only observation

### Phase 2: Land `PatchDraftCompiler` and offline fixtures

Scope:

- add `src/mew/patch_draft.py`
- implement validator and blocker taxonomy
- add replay-bundle persistence for compiler inputs/outputs and draft failures
- add fixture-based compiler tests for happy and negative paths

What this phase proves:

- `#399` can be reproduced as a compiler/blocker problem without a live model
- any live draft failure after Phase 2 leaves a replayable local bundle
- the validator can deterministically accept or reject patch proposals
- replay bundles become the measurement surface for the mandatory Phase 2/3
  calibration checkpoint; Phase 3 should not start until that checkpoint is
  ready to evaluate off-schema and refusal incidence

### Phase 3: Rewire write-ready fast path to patch contract

Scope:

- replace `build_work_write_ready_think_prompt()` with the tiny patch schema contract
- route write-ready model output through `PatchDraftCompiler`
- translate `PatchDraft` into existing dry-run `edit_file` / `edit_file_hunks`

What this phase proves:

- exact cached windows now produce a diff or exact blocker in one narrow turn
- the loop no longer depends on generic tool-batch planning while drafting

Phase 3 entry gate:

- the Phase 2/3 calibration checkpoint from
  `docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md` must be wired and
  ready to evaluate replay-bundle off-schema/refusal ratios before rollout

### Phase 4: Add drafting-specific recovery and follow-status

Scope:

- replace draft-time `replan` with draft-aware recovery actions
- add timeout, refusal, and fallback handling for the patch lane
- surface todo/blocker/action in follow-status and resume

What this phase proves:

- `#401` resumes from the same draft frontier instead of re-exploring
- live failures become directly actionable from resume/follow output

### Phase 5: Add isolated review lane

Scope:

- add structured review contract on top of validated patch artifacts
- attach findings to the active todo
- keep the existing approval/apply flow unchanged in Phases 3-4; Phase 5 inserts review between validated dry-run preview and approval without making memory-provider work a dependency

What this phase proves:

- review no longer depends on full exploratory transcript
- draft correction can be replayed from stable artifacts

### Phase 6: Tighten executor lifecycle states

Scope:

- add `queued`, `executing`, `cancelled`, `yielded`
- add separate cancellation domains
- guarantee terminal records on interruption/fallback
- keep this phase independent of deferred memory-provider protocol work

What this phase proves:

- resumed sessions do not contain orphaned in-flight state
- exploration/runtime stability improves without reopening the drafting design

## Freeze / Defer List

### Freeze now

- Freeze further prompt-only tuning of the current write-ready fast path until phases 1-4 land.
- Freeze the semantics of `src/mew/write_tools.py`; treat it as stable downstream infrastructure.
- Freeze the existing paired `src/mew/**` + `tests/**` code-write policy.
- Freeze dry-run approval/apply/verify gates in `commands.py`.
- Freeze blocker and recovery code names once phase 0 lands.

### Defer intentionally

- Full Claude Code style concurrent read executor across the whole loop.
- Any subagent architecture for exploration or review.
- A free-standing `memory explore agent`; only the read-only provider interface should be designed now.
- Raw patch grammar/CLI compatibility layers like Codex's shell-facing patch tool surface.
- Multi-todo scheduling beyond "exactly one active drafting todo."
- Broad follow-status UX redesign beyond draft-specific observability fields.
- Any roadmap/status file updates tied to this design.

## Appendix: Close-Gate Strengthening

The proposal in `docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md` is
adopted as additive close-gate verification for M6.11. It does not widen the
Phase 0-4 implementation scope, but it does add three required verification
surfaces for milestone close:

1. `m6_11-*` dogfood scenarios covering compiler replay, draft timeout,
   refusal separation, drafting recovery, and phase-4 regression
2. a 20-slice bounded iteration incidence gate for `#399` + `#401`
3. a Phase 2/3 replay-bundle calibration checkpoint that can pause rollout and
   require a Phase 2.5 calibration slice before Phase 3

The important ordering rule is explicit: Phase 2 continues normally, but Phase
3 does not start until the calibration checkpoint exists and is ready to gate
rollout.

## Risks / Tradeoffs

1. More runtime state means more migration pressure.
   The design adds `WorkTodo`, patch artifacts, blocker records, and replay bundles. That is extra complexity, but it replaces unstable prompt behavior with inspectable state.

2. Hash validation may force more targeted rereads.
   This is intentional. It is better to fail as `stale_cached_window_text` than to silently patch against stale context.

3. A tiny patch schema may constrain larger edits.
   That tradeoff is acceptable for the stabilization target. The first goal is to close `#399` and `#401`, not to optimize large refactors.

4. An isolated review phase adds latency.
   True, but only after a validated patch exists. Mew already prefers safety over raw speed at the write boundary.

5. Replay bundles can accumulate and may contain sensitive code context.
   They should be bounded, rotatable, and stored locally under `.mew/`. The debuggability gain is still worth it.

6. Deferring executor changes means explore-side inefficiencies remain for a while.
   That is acceptable because the current instability is draft-side, not primarily read-side.

## Concrete First Tasks

1. Add `WorkTodo` data structures and transitions in `src/mew/work_session.py`, including cached window hashes, verifier hint, and one-active-todo invariants.
2. Extend `recent_read_file_windows` and `plan_item_observations` so exact cached window refs carry stable content hashes and can survive resume/replay.
3. Add `src/mew/patch_draft.py` with `PatchDraft`, `PatchBlocker`, validator rules, and blocker taxonomy.
4. Add replay-bundle persistence for compiler inputs/outputs and for every draft timeout, non-schema response, validator blocker, and review rejection.
5. Add fixture-based tests under `tests/fixtures/work_loop/patch_draft/` and `tests/fixtures/work_loop/recovery/` for `#399`, `#401`, stale cache, ambiguous old text, and missing paired test edit.
6. Replace the current write-ready fast-path prompt in `src/mew/work_loop.py` with the tiny `patch_proposal | patch_blocker` contract.
7. Route validated patch artifacts into the existing dry-run preview flow in `src/mew/commands.py` without changing `write_tools.py` semantics.
8. Split draft-time recovery in `build_work_recovery_plan()` so exact-window timeouts produce `resume_draft_from_cached_windows` instead of generic `replan`.
9. Extend `work --follow-status` and `build_work_session_resume()` to surface `todo_id`, blocker code, attempt count, runtime mode, and next recovery action.
10. Add prompt-budget and prompt-contract metrics so drafting retries can prove they reuse the same stable prefix and only shrink/change the dynamic suffix.
11. Define a read-only `MemoryExploreProvider` interface that plugs into the explore handoff contract without adding a second autonomous planner.
12. Freeze provisional `MemoryExploreRequest/Result` field lists and the memory-provider replay bundle format before any agent backend exists.
13. Only after steps 1-10 are green, add the isolated review lane and then executor lifecycle tightening. Steps 11-12 are deferred protocol work and are not blockers for Phase 5 or Phase 6.
