# Mew Loop Structure Review (2026-04-22)

## Executive Summary

Mew already models the pre-drafting state better than the drafting state itself. The path from search/read to `edit_ready` is explicit and fairly well tested in `src/mew/work_session.py`, but once exact cached windows exist, the loop still depends on a single model turn to synthesize a valid paired dry-run patch. That is the main structural gap behind both known buckets:

- `#399`: exact cached windows exist, but there is no deterministic bridge from those windows to a safe dry-run patch or an exact blocker.
- `#401`: exact cached windows are reached, but drafting is still one large model call with weak retry/recovery semantics, so a timeout stops the loop before any draft exists.

The highest-value problems are:

- `edit_ready` is an observation, not a drafting contract.
- write-ready fast path activation is narrower and more brittle than the underlying cached-window state.
- drafting timeouts are treated as generic model failures, while interrupted tools get specialized recovery.
- refusal/parse failures are not first-class work-loop outcomes.
- current tests validate many local mechanics, but they do not replay the real failure buckets end-to-end.

## Structural weak points in mew today

### 1. Search/read -> cached windows is explicit; cached windows -> patch is still implicit

`src/mew/work_session.py:4691-4841` builds `requested_window`, `cached_windows`, and `plan_item_observations[0].edit_ready`. That gives the loop a good notion of "the necessary source/test text is already present."

But the next step is still prompt-only. `src/mew/work_loop.py:1203-1253` narrows context for write-ready mode, and `src/mew/work_loop.py:1386-1400` tells the model to draft a paired dry-run batch "now." There is no structural component that:

- converts exact cached windows into candidate `edit_file` / `edit_file_hunks` calls,
- validates that every proposed hunk is grounded in cached text before the model turn finishes,
- or degrades to one exact blocker with file/span-level specificity.

That makes `edit_ready` advisory rather than executable. When the model hesitates, drifts, or returns non-drafting JSON, the loop has no drafting-specific fallback.

### 2. Write-ready fast path is brittle at activation and slightly leaky at context selection

`src/mew/work_loop.py:1087-1124` only activates write-ready fast path when all of these are true:

- the first plan item is `edit_ready`,
- there are at least two cached windows,
- the windows include both `tests/**` and `src/mew/**`,
- and if steer/guidance text exists, it must contain write-ish words such as `dry-run`, `dry run`, or `draft`.

That last gate is structurally brittle. The loop may have exact cached windows and a paired source/test target, but a recover/retry steer that says "continue" or "finish the interrupted step" disables the optimization with `guidance_not_requesting_write`.

`src/mew/work_loop.py:1163-1200` is also slightly leaky. It first tries to recover the exact cached spans from `recent_read_file_windows`, but if those exact spans are absent it falls back to broader target-path windows via `_write_ready_recent_windows_from_target_paths()`. That is useful for resilience, but it weakens the contract from "exact cached windows are available" to "some recent windows on those target paths are available." For `#399`, that means the loop can enter a drafting-shaped mode without preserving a strict exact-span invariant end-to-end.

### 3. Drafting budget behavior is too simple for the failure surface

`src/mew/work_loop.py:1907-1974` extends THINK timeout to `90s` on write-ready fast path, records metrics, and then still does one model call. The structure around that call is fragile for `#401`:

- `src/mew/work_loop.py:107-159` hard-disables transient retries by default with `retry_delays=()`, even though the base agent retry path in `src/mew/agent.py:359-416` treats timeouts, 5xx, connection issues, and JSON parse failures as transient.
- If streaming deltas are enabled, `src/mew/work_loop.py:117-123` bypasses the forked hard-timeout guard entirely and calls the generic agent wrapper directly.
- If the timeout-guard child crashes, `src/mew/work_loop.py:148-150` falls back to `_call_model_json_without_guard()`, which removes the hard guard for that request.

So the loop has only one real budget move for drafting: "raise timeout to 90s." It does not have:

- a bounded second drafting attempt with a smaller prompt,
- residual-budget management across recovery,
- or a drafting-specific fallback when the model spends the whole budget without yielding a patch.

### 4. Prompt assembly is doing too much policy work inside one instruction block

`src/mew/work_loop.py:1334-1382` is a long instruction bundle that mixes:

- navigation heuristics,
- cached-window reuse rules,
- write batching constraints,
- verifier selection,
- continuity/recovery behavior,
- and finish/wait rules.

The fast path reduces prompt size, but only after the loop has already decided that fast path is active. For non-fast-path drafting turns, the model still receives a large, policy-heavy instruction set. That creates two structural risks:

- the model spends budget satisfying prompt policy instead of emitting the draft,
- and small prompt shifts can move behavior between reread / wait / write in unstable ways.

This is especially relevant because `src/mew/reasoning_policy.py:84-127` promotes any task/guidance containing terms such as `policy` or `recovery` to `high` reasoning effort. For loop-stabilization work, those words are common, so the drafting turn can become both larger and slower exactly when the loop most needs predictable execution.

### 5. Recovery is much stronger for tools than for interrupted drafting

`src/mew/work_session.py:3991-4249` contains a fairly mature recovery planner for interrupted tools:

- `retry_tool`
- `retry_dry_run_write`
- `retry_apply_write`
- `verify_completed_write`
- `retry_verification`

By contrast, interrupted model turns with no committed tool result are collapsed to one generic item at `src/mew/work_session.py:4212-4229`:

- `action: "replan"`
- `reason: "interrupted model planning has no committed tool result; verify world state and run a new work step"`

That loses the critical distinction between:

- "we timed out before we found the files" and
- "we already had exact cached windows and only needed to emit the dry-run patch."

This is the main recovery asymmetry behind `#401`. Tool interruptions preserve operation-specific semantics; drafting interruptions do not.

### 6. Refusal handling is not modeled as a first-class work-loop outcome

`src/mew/codex_api.py:86-109` and `src/mew/codex_api.py:125-131` merge `response.refusal.delta` into normal text extraction. `src/mew/codex_api.py:283-288` then attempts JSON extraction and raises `failed to parse JSON plan: ...; raw=...` on refusal-shaped non-JSON text.

At the work-loop level, that generally lands as a backend/model failure, not as a structured planning result such as:

- `wait` with a classified refusal reason,
- `ask_user` for missing approval/context,
- or `finish` with an explicit refusal-policy explanation.

There is a separate safety/approval boundary in `src/mew/self_improve_audit.py:28-49`, `468-535`, but that is an execution/approval control for self-improvement work, not a general drafting-time refusal primitive. Structurally, refusal is still "transport or parse failure first, policy meaning second."

## Evidence in source/tests

### Source evidence

- `src/mew/work_session.py:4691-4841`
  - Resume logic computes `requested_window`, `cached_windows`, `edit_ready`, and carries them into `resume`.
- `src/mew/work_loop.py:1087-1253`
  - Fast-path state/details/context derive a narrowed drafting context from cached windows, but do not produce a patch.
- `src/mew/work_loop.py:1334-1400`
  - Think prompts encode the drafting policy and fast-path drafting instructions.
- `src/mew/work_loop.py:1907-1974`
  - Fast path only changes prompt/context and THINK timeout; it does not change retry/recovery structure.
- `src/mew/work_loop.py:107-159`
  - Work-loop model calls disable transient retries and only enforce a hard guard in some non-streaming cases.
- `src/mew/work_session.py:3991-4249`
  - Tool recovery is typed and specific; model-turn recovery is generic `replan`.
- `src/mew/commands.py:4059-4124`
  - Model failure is recorded and the live loop stops with `stop_reason = "model_error"`.
- `src/mew/commands.py:6491-6808`
  - Follow status surfaces prompt/timeout/fast-path metrics, but suggested recovery still routes through generic resume/replan paths.
- `src/mew/codex_api.py:86-109`, `125-131`, `283-288`
  - Refusal deltas are flattened into text and typically fail later as JSON parsing/back-end errors.
- `src/mew/write_tools.py:363-495`
  - Write tools themselves are strict and structurally sound; once exact old text exists, patch application is not the weak point.

### Existing tests that already cover useful pieces

- `tests/test_work_session.py:6143-6161`
  - Confirms prompt/context prefer paired dry-run drafting once `edit_ready` is true.
- `tests/test_work_session.py:6163-6238`
  - Confirms fast path can fall back from exact cached spans to broader target-path recent windows.
- `tests/test_work_session.py:6240-6289`
  - Confirms explicit `missing_exact_cached_window_texts` fast-path failure reason.
- `tests/test_work_session.py:6291-6388`
  - Confirms an uncached exact read window blocks `edit_ready`.
- `tests/test_work_session.py:6392-6487`
  - Confirms a cached exact read plan item can be skipped and fast path can activate.
- `tests/test_work_session.py:6682-6791`
  - Confirms fast path raises THINK timeout to `90s`.
- `tests/test_work_session.py:6894-6996`
  - Confirms work-loop model calls disable transient retries, enforce a hard timeout in the guarded case, and fall back after child crash.
- `tests/test_work_session.py:15533-15590`
  - Confirms compact recovery context after timeout with pending steer.
- `tests/test_work_session.py:21246-21545`
  - Confirms follow-status reports overdue model timeouts, latest failure metrics, and generic replanning recovery.
- `tests/test_write_tools.py:42-174`
  - Confirms `edit_file` / `edit_file_hunks` enforce exact old text, reject ambiguous matches, and handle multi-hunk edits atomically.

### Coverage gaps against the known buckets

There is still no test that directly models `#399`:

- exact cached source/test windows exist,
- write-ready fast path is active,
- the model returns `wait`, malformed JSON, or a non-drafting response,
- and the loop is expected to either synthesize a safe dry-run patch or emit one exact blocker.

There is also no end-to-end test that directly models `#401`:

- exact cached windows exist,
- fast path is active,
- the model times out during drafting,
- and recovery is expected to preserve "resume drafting from cached windows" rather than generic replanning.

The current suite validates the pieces around those failures, but not the failures themselves as replayable loop regressions.

## Missing replay / harness design

### 1. Captured-session replay for `#399`

Add a replay fixture that contains:

- session `tool_calls` with the exact cached source/test windows,
- `resume.plan_item_observations[0].edit_ready = true`,
- `recent_read_file_windows` with non-truncated exact text,
- and the real or synthetic model output that failed to produce a dry-run patch.

The harness should assert one of two acceptable outcomes:

- a valid paired dry-run batch grounded in the cached text, or
- `wait` with one exact blocker naming the file/span or missing invariant.

This should not allow generic reread/search fallback, because that is exactly what `#399` is trying to stabilize away.

### 2. Timeout replay for `#401`

Add a replay fixture that starts from the same write-ready state and forces a THINK timeout. The regression should assert:

- timeout is recorded with fast-path metrics,
- recovery preserves the drafting-specific state,
- and the next suggested action is something like `resume_draft_from_cached_windows`, not generic `replan`.

This should be an end-to-end live/follow-style test, not only a unit test of `plan_work_model_turn()`.

### 3. Drafting convergence harness

Add a small harness around the drafting contract itself:

- input: focused write-ready context with exact cached windows,
- output: normalized action,
- invariant checks:
  - every write path is in the cached window set,
  - every `old` string appears exactly in cached text,
  - same-file multi-hunk edits collapse into `edit_file_hunks`,
  - failure degrades to one exact blocker.

This would test the loop at the boundary that matters, instead of only testing prompt construction.

### 4. Timeout/retry matrix harness

Add a parameterized harness for:

- streaming vs non-streaming,
- guarded vs unguarded model call,
- child-crash fallback,
- transient parse failure,
- backend timeout.

The current tests cover several of these in isolation, but not the policy matrix. The missing case that matters most is streaming fast-path drafting, where `on_text_delta` disables the forked guard in `src/mew/work_loop.py:117-123`.

### 5. Refusal-policy harness

Add tests that force refusal-shaped responses from Codex and assert work-loop classification. Today there is no direct work-loop test showing that:

- refusal deltas become a structured `wait` / `ask_user`, or
- refusal is distinguishable from generic `failed to parse JSON plan`.

Without that harness, refusal behavior will continue to look like backend instability.

## Highest-value fixes next

1. Introduce a drafting-specific state transition after `edit_ready`.
   - Add an explicit "cached windows are now the drafting source of truth" phase or recovery item.
   - Preserve that state across timeout/reentry instead of collapsing it into generic replanning.

2. Add a deterministic dry-run patch/blocker synthesizer for write-ready mode.
   - It does not need to replace the model completely.
   - It does need to validate that every proposed edit is grounded in cached text and to emit one exact blocker when it cannot proceed.

3. Split drafting recovery from generic model failure.
   - Replace model-turn `replan` for write-ready timeouts with a drafting-specific action such as `resume_draft_from_cached_windows`.
   - Surface that directly in `build_work_recovery_plan()` and follow-status output.

4. Make drafting timeout behavior uniform.
   - Preserve a hard total deadline in streaming mode.
   - Do not silently fall back to an unguarded path after timeout-guard child failure without recording that degraded mode.
   - Allow one bounded retry for write-ready drafting only, using the reduced fast-path prompt.

5. Relax fast-path activation to depend on state, not wording.
   - If the first plan item is `edit_ready` and paired cached windows exist, activation should not depend on whether steer text happens to contain `draft` or `dry-run`.

6. Add replay fixtures for `#399` and `#401` before broad prompt changes.
   - These bugs are structural enough that they need session-level regression fixtures, not only more prompt heuristics.

## What not to change yet

- Do not weaken `src/mew/write_tools.py` exact-match semantics.
  - The strict `old`-text requirement is a good safety boundary. The instability is upstream in drafting, not in patch application.

- Do not remove the paired `tests/**` + `src/mew/**` write discipline yet.
  - That constraint is annoying for the model, but it is carrying real safety and review value for mew-internal changes.

- Do not solve `#399`/`#401` by simply increasing timeout again.
  - `90s` is already a sign that the drafting step is structurally heavy. More timeout without better state/recovery will mostly make failures slower.

- Do not replace compact recovery context first.
  - `compact_model_turns_for_prompt()` is not the core problem. The bigger issue is that the loop does not preserve drafting-specific semantics after timeout.

- Do not fold refusal handling into generic timeout recovery.
  - Refusal should become more explicit, not less explicit.
