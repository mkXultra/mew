# Recommendation

Choose **(b) authoritative dispatch only**, in the narrowest guarded form:

- keep the current write-ready prompt unchanged
- keep the current outer model action contract unchanged
- promote the already-landed shadow bridge from metrics/replay-only observation to **authoritative execution** for write-ready adapted edit actions
- if the shadow bridge cannot adapt or isolate cleanly, fall back to the existing action semantics exactly as current HEAD does

This is smaller and safer than a combined prompt swap + dispatch slice, and prompt swap only is not safe to land by itself.

# Why this is the next smallest safe slice

Current HEAD `6152a47` already has:

- offline compiler validation in `src/mew/patch_draft.py`
- offline preview translation in `compile_patch_draft_previews()`
- shadow-mode adaptation, replay capture, and exception isolation in `src/mew/work_loop.py`
- integration coverage in `tests/test_work_session.py` for:
  - validated shadow compile
  - blocker shadow compile
  - unadapted no-replay fallback
  - inactive-path skip
  - replay-writer exception isolation

That means the remaining gap is no longer "can we adapt the current write-ready action into compiler inputs?" The repo already proves that in shadow mode. The next smallest step is therefore to **flip authority in the command path** for the already-proven write-ready adapted actions, while leaving the prompt contract alone for one more slice.

Why not the other options:

- **(a) prompt swap only**: unsafe. The live bridge is not authoritative yet, so swapping the model contract first would strand the runtime on a new schema before the command path actually consumes it.
- **(c) combined prompt swap + authoritative dispatch**: larger than necessary. It mixes model-contract risk and command-dispatch risk in one change when current HEAD has already isolated the dispatch seam in shadow mode.
- **(d) some narrower bridge**: the only narrower bridge that still changes behavior is this guarded authoritative-dispatch flip on the existing write-ready surface. Anything smaller is still just observation.

# Exact files to touch

- `src/mew/work_loop.py`
  - extend the shadow helper / `plan_work_model_turn()` return shape so the command path gets the structured shadow outcome it needs authoritatively, not just flattened metrics
  - keep `build_work_write_ready_think_prompt()` and `WORK_WRITE_READY_DRAFT_PROMPT_CONTRACT_VERSION` unchanged in this slice
  - preserve the current fallback semantics when the action is unadapted or the shadow helper records an exception

- `src/mew/commands.py`
  - when a planned turn is on the write-ready fast path and the shadow bridge produced a validated `PatchDraft` + preview translation, execute the translated preview actions instead of the raw model batch
  - when the bridge produced a `PatchBlocker`, stop the step without write tool calls or pending approvals and surface the blocker/replay outcome on the model turn / step report
  - when the bridge produced `unadapted` or `exception`, keep the current outer action behavior unchanged

No source changes should be needed in:

- `src/mew/patch_draft.py`
- `src/mew/work_replay.py`
- `src/mew/write_tools.py`

# Tests to add or update

Primary test module:

- `tests/test_work_session.py`

Add or update tests for:

1. **Authoritative validated dispatch**
   - current write-ready generic batch still comes from the model
   - command path executes the translated preview actions, not the raw model batch
   - resulting tool calls / pending approvals remain the same existing dry-run preview shape

2. **Authoritative blocker stop**
   - shadow bridge yields `patch_blocker`
   - no write tool calls are emitted
   - no pending approvals are created
   - replay path / blocker outcome is attached to the turn or step report

3. **Fallback on unadapted**
   - if the shadow bridge says `unadapted`, the existing action path still runs unchanged

4. **Fallback on shadow exception**
   - if the shadow bridge records `exception`, the existing action path still runs unchanged
   - the turn records the shadow error without turning the whole step into a command-path failure

5. **No prompt change**
   - existing prompt-contract assertions for write-ready mode remain unchanged in this slice

No new tests should be added yet for:

- prompt-swap-specific patch schema prompting
- draft-time recovery routing
- follow-status / resume rendering

# Acceptance criteria

1. On the current write-ready fast path, a model-produced generic edit batch that shadow-compiles cleanly is executed through the translated preview specs, not through the raw model batch.
2. The resulting write tool calls, diff previews, and pending approvals remain the same existing dry-run surfaces used today.
3. If the authoritative bridge yields `patch_blocker`, the step emits no write tool calls and no pending approvals.
4. If the bridge yields `unadapted` or `exception`, the command path falls back to the exact current behavior.
5. Replay capture continues to be written for adapted write-ready shadow/authoritative outcomes.
6. No prompt swap occurs in this slice.

# Explicit non-goals

- do not change `build_work_write_ready_think_prompt()`
- do not introduce the tiny `patch_proposal | patch_blocker` prompt contract yet
- do not add Phase 4 recovery behavior:
  - no `build_work_recovery_plan()` changes
  - no `resume_draft_from_cached_windows`
  - no follow-status or resume UX expansion
- do not insert the review lane
- do not change `write_tools.py` semantics
- do not widen the bridge beyond the existing write-ready fast path

# Implementation note

This slice should be treated as the **authority flip on top of the landed shadow bridge**. Once that works and is covered, the following slice can safely do the actual prompt swap, because the runtime will already know how to consume authoritative `PatchDraft` / `PatchBlocker` outcomes.

## Addendum: Calibration Collection Gate

Given current HEAD produces `ok=false` with `replay root not found` for `mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json`, the next step is now **a Phase 2.5 calibration collection step, not more Phase 3 implementation yet**.

Concrete consequence:

- do **not** start the authoritative-dispatch slice yet
- first run bounded real shadow-mode work sessions until `.mew/replays/work-loop/...` exists and `proof-summary --m6_11-phase2-calibration` can evaluate a non-empty replay surface
- once shadow bundles exist and the checkpoint is actually measurable, resume the authoritative-dispatch slice described above

Reason: the shadow bridge was landed to create the live measurement surface before turning the bridge authoritative. Right now that surface does not exist, so proceeding straight to authoritative dispatch would skip the intended pre-rollout observation step rather than using it.

## Addendum: Live Shadow Evidence From Task #402

This supersedes the earlier "authoritative dispatch only" recommendation.

Live shadow collection now shows:

- the replay root exists
- both collected bundles are `work-loop-model-failure.request_timed_out`
- `compiler_bundles = 0`
- `patch_draft_compiler_ran = false`
- `prompt_chars` are still about `41k-42k`
- `active_memory_chars` are about `13k`
- `tool_context_chars` are about `57k`

That means the current write-ready call is still too large to produce any draft artifact at all. The blocker is now **prompt size before draft generation**, not command-path authority.

### Revised next slice

The next smallest safe slice is now **(d) a narrower bridge**:

- add a **write-ready-only tiny draft call** that asks only for `patch_proposal | patch_blocker`
- if that tiny call returns a draft artifact, consume it authoritatively through `compile_patch_draft()` + `compile_patch_draft_previews()` and the existing dry-run preview path
- if that tiny call times out, errors, or returns unusable output, **fall back to the current generic work action path unchanged**

So the next slice is **not** prompt swap only, and it is **not** authoritative dispatch only. It is a guarded combined bridge: tiny draft call + authoritative consumption + hard fallback to the current runtime path.

### Smallest safe shape

Production files:

- `src/mew/work_loop.py`
  - add a tiny write-ready draft prompt/context builder that only includes:
    - active todo id
    - target paths
    - exact cached window texts / hashes for the paired source+test frontier
    - verify command / allowed write roots
    - a minimal `patch_proposal | patch_blocker` schema
  - add a dedicated write-ready draft model call with no ACT pass and a tighter timeout than the current large work prompt
  - return a structured result that tells the command path whether the tiny draft call produced:
    - validated candidate artifact
    - blocker artifact
    - timeout / exception / unusable output

- `src/mew/commands.py`
  - if the tiny draft call yields a usable patch artifact, consume it authoritatively
  - if it yields blocker, stop without write tool calls
  - if it yields timeout / exception / unusable output, execute the current generic action path exactly as today

Tests:

- `tests/test_work_session.py`
  - add one happy-path test for tiny draft call -> authoritative preview dispatch
  - add one blocker test for tiny draft call -> no write tool calls
  - add one fallback test where tiny draft call times out and the existing generic action path still runs
  - add one metrics test that the tiny draft prompt is materially smaller than the current write-ready prompt and records separate prompt-size / fallback fields

### Acceptance criteria

1. On write-ready turns, mew attempts the tiny draft call before the current large generic call.
2. If the tiny draft call succeeds, the runtime consumes the patch artifact authoritatively and uses the existing dry-run preview flow.
3. If the tiny draft call fails or times out, the runtime falls back to the current generic behavior without stranding the step.
4. Non-write-ready turns remain unchanged.
5. No Phase 4 recovery work is introduced in this slice.

### Explicit non-goal

Do **not** replace the current generic prompt outright in this slice. The fallback path is what keeps the runtime from being stranded while the tiny draft lane is proving itself under real timeout pressure.
