# Mew Loop Stabilization Synthesis (2026-04-22)

## Executive Summary

All three reference audits (Claude Code patterns, Codex patterns, and mew's own structure review) converge on one finding: **mew has good pre-drafting observation, but no drafting contract**. The loop can detect `edit_ready`, it can narrow the prompt, it can extend the timeout — but when the model reaches the write-ready state, there is still exactly one unstructured model turn between cached windows and a dry-run patch. Both failure buckets live in that single turn:

- `#399` — exact cached windows exist, but the loop has no deterministic bridge from cached text to a dry-run patch or an exact blocker. Model drifts into reread/wait/malformed output and the loop silently regresses to exploration.
- `#401` — exact cached windows are reached, the model turn is large enough that timeout is a normal outcome, and recovery collapses into generic `replan` rather than resuming drafting from the same cached windows.

The recommended structural change is to **insert a Patch Draft Compiler + Work Todo ledger between `edit_ready` and the existing dry-run write tools**, and to re-route recovery so drafting state is first-class. This directly borrows:

- Codex's **patch IR + deterministic validator + blocker taxonomy** (`apply-patch/src/parser.rs`, `invocation.rs`).
- Claude Code's **session-scoped todo ledger** with exactly one `in_progress` item, plus executor lifecycle states.
- Mew's own recommended **drafting-specific state transition and recovery item**.

The synthesis is opinionated: **stop tuning prompts, build a compiler boundary.** Treat drafting as "cached windows → patch IR → validated diff," not "large model turn emitting tool calls." Everything downstream (approval, reviewer log, apply, verify) can reuse that single payload.

This is the highest-leverage change because it:

1. Converts `edit_ready` from an advisory observation into an executable contract.
2. Shrinks the write-ready model call to "emit patch IR or one exact blocker," which is both cache-friendly and timeout-friendly.
3. Gives drafting timeouts a specific recovery lane instead of merging them into generic `replan`.
4. Makes the failure buckets replayable offline without a live model.

---

## Core diagnosis

Mew's drafting path today is a three-phase pipeline with a missing middle:

```
explore / read  →  [edit_ready observed]  →  one large model turn  →  dry-run write tool call
                                             ^
                                             missing: structured drafting contract
```

Consequences visible across all three audits:

| Symptom | Root cause | Evidence |
| --- | --- | --- |
| Cached windows exist but no patch appears (#399) | `edit_ready` is an observation on `plan_item_observations`, not an input to a compiler that owns `patch_draft` or `blocker` | mew review: "`edit_ready` is an observation, not a drafting contract"; Codex review: no separate "syntax → semantic verifier" layer |
| Draft times out, reentry re-explores (#401) | Drafting has no terminal state; timeout flips the loop into generic `replan` which loses drafting-specific context | mew review §5; Claude Code review: executor only has running/completed/failed; no yielded/cancelled |
| Fast path flickers off on innocuous steer words | Activation gated on prompt wording (`draft`, `dry-run`) rather than persisted state | mew review §2 |
| Refusal is indistinguishable from backend error | Refusal deltas flattened into text, surfaced as JSON parse failure | mew review §6 |
| Sibling reads cancel on first error | Batch executor has one cancellation domain | Claude Code review §5 |

The unifying diagnosis: **mew currently lets the model be both the planner and the compiler for writes.** Every other boundary in mew has been moved out of the prompt (tool schema, approvals, exact-match write semantics, recovery planner for interrupted tools). The drafting boundary is the last one that still lives inside model prose.

---

## Missing structural layer

Mew is missing a single named layer that can be described in one sentence:

> **A Patch Draft Compiler, owned by a persisted Work Todo, that takes `(plan_item, cached_windows, write_policy)` and returns either a validated `patch_draft` (file, hunks, unified_diff) or one classified `blocker`.**

This layer does not need to replace the model. It needs to constrain the model's contribution to exactly the part that is hard to verify deterministically (which text to change), and to deterministically verify everything else (where the text lives, whether it is still there, whether the hunks overlap, whether the diff is empty).

Why this is the right layer, and not any of the adjacent ones:

- **Not a bigger prompt.** Codex and Claude Code both demonstrate the same conclusion: prompt-level contracts drift; tool/IR-level contracts hold. Mew has already spent iteration budget on prompt tuning (`build_work_write_ready_think_prompt()`, fast-path narrowing); returns are diminishing.
- **Not a new sub-agent.** Neither audit recommends copying Claude Code's agent marketplace or Codex's isolated reviewer task *yet*. Those come after the compiler exists; a sub-agent with no contract to pass would just move the ambiguity.
- **Not a stricter write tool.** `src/mew/write_tools.py` is already strict and correct. Strengthening it further punishes recoverable drafts. The gap is upstream — between "exact text cached" and "write tool invoked."
- **Not a bigger todo system.** The global `tasks.py` is orthogonal. The missing ledger is *session-scoped* and exists specifically to carry the drafting frontier across timeouts.

The Patch Draft Compiler sits at the same architectural altitude as Codex's `apply-patch` crate: a deterministic module that can be tested offline with fixtures, that has a small, frozen input/output contract, and that produces the single payload consumed by preview, approval, reviewer logging, apply, and verify.

---

## Recommended architecture change

Introduce three cooperating components. They are small, land in existing modules, and each unlocks the next.

### 1. `WorkTodo` — persisted drafting frontier

A new session-scoped record, distinct from `working_memory.plan_items` (which stays as derived state from model output). One `WorkTodo` per in-progress drafting step.

Fields:

- `id`
- `status` — `pending | drafting | blocked | dry_run_ready | approved | applied | verified | completed`
- `target_paths` — paired source/test paths
- `cached_window_refs` — exact spans (file, start, end, content_hash) recovered from `recent_read_file_windows`
- `patch_draft` — validated IR (see below) when present
- `blocker` — one classified reason when present (see taxonomy below)
- `verify_command`
- `attempts` — counter for bounded retry budgeting

Invariants:

- Exactly one todo in `drafting` at a time (Claude Code pattern).
- Transitions are tool-backed mutations, not model prose (Claude Code pattern).
- Todo survives model timeout, process restart, and resume (Claude Code + mew review).
- Cached-window refs are by content hash — stale cache is a first-class blocker, not a silent rebroadening (mew review §2).

Lands in: `src/mew/work_session.py`, touched by `src/mew/work_loop.py`.

### 2. `PatchDraftCompiler` — deterministic bridge

A pure module. No model calls. No filesystem mutation. It accepts `(WorkTodo, model_patch_proposal)` and returns `PatchDraft | PatchBlocker`.

Input from model (tiny contract):

```
{
  "kind": "patch_proposal",
  "hunks": [
    {"path": "...", "old": "...", "new": "..."}
  ]
}
```

OR

```
{
  "kind": "blocker",
  "reason": "<taxonomy code>",
  "detail": "..."
}
```

Output:

- `PatchDraft { per_file: [{path, old_content_hash, new_content, unified_diff}] }`
- `PatchBlocker { code, path, span?, detail }`

Validator responsibilities (Codex pattern):

- Every `old` text appears exactly once in the relevant cached window.
- No hunks overlap on the same file.
- Resulting `new_content` differs from current on-disk content.
- Cached window content hash still matches current disk.
- Target paths are inside the write policy allowlist (paired `src/mew/**` + `tests/**`).

Blocker taxonomy (frozen, replayable):

- `missing_exact_cached_window_texts`
- `stale_cached_window_text` (content hash mismatch)
- `ambiguous_old_text_match` (more than one occurrence)
- `old_text_not_found`
- `overlapping_hunks`
- `no_material_change`
- `unpaired_source_edit_blocked`
- `write_policy_violation`
- `model_returned_non_schema`
- `model_returned_wait_with_no_reason` (refusal shape)

Lands in: new `src/mew/patch_draft.py`, consumed by `src/mew/work_loop.py` and `src/mew/commands.py`.

### 3. Drafting-specific recovery lane

Split the current generic `replan` into drafting-aware actions (mew review §5):

- `resume_draft_from_cached_windows` — re-enter compiler with same `WorkTodo`, reduced prompt, smaller bounded retry.
- `draft_timeout_bounded_retry` — one additional attempt with identical cached windows but freshly re-verified hashes.
- `draft_blocker_surface` — classified blocker becomes a `wait` with the taxonomy code, not a parse error.
- `explore_reopen` — only if cached windows have become stale and the compiler says so, not because the model failed silently.

Lands in: `src/mew/work_session.py::build_work_recovery_plan()`, surfaced in `src/mew/commands.py` follow-status.

### How this fixes the buckets

- **#399**: When `edit_ready` becomes true, the next model turn has exactly one job — emit `patch_proposal` or one `blocker` against the compiler's schema. If the model returns wait or malformed JSON, the compiler returns `model_returned_non_schema` and the loop advances the `WorkTodo` into `blocked` with a specific reason. No silent regression to exploration.
- **#401**: The draft turn is a tiny model call (todo + cached text + schema, ~2-3k chars instead of the current policy-heavy instruction bundle). Timeout becomes rarer. When it does happen, recovery stays inside `drafting` status with the exact same `cached_window_refs`, runs one bounded retry, and surfaces a drafting-specific wait rather than generic replan.

---

## Ordered implementation plan

Each step is independently landable and independently testable. Earlier steps must precede later ones; do not parallelize.

### Step 1 — `WorkTodo` record and transitions (architecture)

- Add `WorkTodo` dataclass and session-scoped store to `src/mew/work_session.py`.
- Add transition functions: `open_todo`, `advance_todo`, `block_todo`, `complete_todo`.
- Bind `WorkTodo` lifecycle to existing loop boundaries: create on explore completion, advance on dry-run success, complete on verify.
- No prompt changes yet.

Acceptance: a session can be resumed with a persisted `WorkTodo` in `drafting` and the loop recognizes it as the current frontier, bypassing re-derivation.

### Step 2 — `PatchDraftCompiler` as offline module (architecture)

- Land `src/mew/patch_draft.py` with `PatchDraft`, `PatchBlocker`, `compile(todo, proposal)`.
- Wire cached-window content hashing in `src/mew/work_session.py` (already nearly present via `recent_read_file_windows`).
- No loop wiring yet. Unit-testable in isolation.

Acceptance: fixture scenarios (see harness section) pass offline with no model in the loop.

### Step 3 — Tiny drafting contract (prompt + compiler integration)

- Replace the current write-ready fast-path prompt with a minimal "emit `patch_proposal` or `blocker`" contract.
- Route the model response through `PatchDraftCompiler` before any tool call is scheduled.
- On `PatchDraft`, synthesize the dry-run write tool calls from validated IR. **The model never writes tool-call JSON in write-ready mode after this step** — only patch IR.
- On `PatchBlocker`, advance `WorkTodo` to `blocked` with the taxonomy code.

Acceptance: a replay with pre-captured cached windows and a mock model returning patch IR produces the same dry-run diff as today's best case, without a second model turn.

### Step 4 — Drafting-specific recovery lane (architecture)

- Split `build_work_recovery_plan()` so drafting timeouts/interruptions map to `resume_draft_from_cached_windows` with the same `WorkTodo`.
- Add `attempts` budgeting: one bounded retry of the tiny draft contract, then surface a blocker.
- Update follow-status output in `src/mew/commands.py` to show drafting-specific state.

Acceptance: forced THINK timeout replay shows recovery preserves `WorkTodo` and re-enters the tiny contract, not explore/replan.

### Step 5 — Refusal classification (small, isolated)

- In `src/mew/codex_api.py`, separate refusal-shaped outputs from transport/parse errors before they reach the work loop.
- Refusals become `model_returned_wait_with_no_reason` blockers with the original refusal text attached.

Acceptance: a refusal-shaped fixture produces a classified blocker, not `failed to parse JSON plan`.

### Step 6 — Relax fast-path activation gate (small)

- Gate on persisted state (`edit_ready` + paired cached windows + active `WorkTodo`), not on steer text wording.
- Remove the `guidance_not_requesting_write` disable path.

Acceptance: steer text `continue` or `finish the interrupted step` does not disable the fast path when state supports it.

### Step 7 — Executor lifecycle states (deferred architecture)

- Add `queued | executing | completed | cancelled | yielded` to tool call state.
- Concurrency-safe reads: `read_file`, `search_text`, `glob`, `inspect_dir`, `git_status`, `git_diff`, `git_log`.
- Selective sibling cancellation (read batch != write batch != verify batch).
- Terminal records on interrupt/fallback.

This is Claude Code's largest pattern, and it stabilizes the *explore* half. It is deferred because steps 1–6 are sufficient to close #399 and #401. Land it only once the drafting path is stable and the replay harnesses exist for the read path too.

Acceptance: interrupt/fallback replay shows no `running` tool call surviving into the next turn.

### Step 8 — Isolated patch reviewer (deferred)

- Once drafts are a single artifact, add an isolated review contract (Codex pattern): reviewer sees only `diff + cached windows + verify hint`, returns structured JSON. No exploratory transcript access.

Deferred because it only pays off once step 2 lands — before that, there is nothing stable to review.

---

## Replay / regression harness plan

The minimum set of harnesses to land *alongside* the architectural changes, not after. Each is scoped to one failure bucket or one contract boundary.

### A. Cached-window → patch scenario directory (blocks #399)

Structure, borrowed from Codex `apply-patch/tests/fixtures/scenarios/`:

```
tests/fixtures/patch_draft/<scenario_name>/
  plan_item.json            # input
  cached_windows.json       # input (file, span, content)
  disk_state/               # input (actual files at that moment)
  model_proposal.json       # input (synthetic model output)
  expected_draft.diff       # expected output — OR
  expected_blocker.json     # expected output (taxonomy code + detail)
```

Required initial scenarios:

- `happy_path_paired_edit` — source + test edit, both cached, compiler returns valid diff.
- `stale_window_hash_mismatch` — cached text valid at capture, disk drifted → `stale_cached_window_text`.
- `ambiguous_old_text` → `ambiguous_old_text_match`.
- `overlapping_hunks_same_file` → `overlapping_hunks`.
- `empty_hunk_after_apply` → `no_material_change`.
- `unpaired_source_only` → `unpaired_source_edit_blocked`.
- `model_returned_explanatory_prose` → `model_returned_non_schema`.
- `refusal_shaped_wait` → `model_returned_wait_with_no_reason`.

Best target: new `tests/test_patch_draft.py`.

### B. Drafting timeout replay (blocks #401)

Session-level fixture: pre-populated session with `WorkTodo.status = drafting`, exact cached windows, THINK timeout forced on the next model call.

Assertions:

- Timeout recorded with fast-path metrics (existing behavior preserved).
- `WorkTodo` remains in `drafting`, not demoted to `blocked` or cleared.
- Recovery plan surfaces `resume_draft_from_cached_windows`, not `replan`.
- One bounded retry attempts the tiny contract; second timeout surfaces a blocker.

Best target: `tests/test_work_session.py` (extend the existing recovery tests there).

### C. Explore → draft handoff

Fixture: two-step session where explore completes and emits only `{target_paths, cached_window_refs, candidate_edit_paths}`. Draft step runs from that state alone.

Assertions:

- Explore phase cannot schedule writes (tool surface enforcement).
- Draft phase consumes refs directly, issues no rediscovery reads.
- Prompt char count in draft phase is below a fixed budget and below the generic resume prompt.

Best target: `tests/test_work_session.py` + one new prompt-budget assertion helper.

### D. Streaming vs guarded timeout matrix

Parameterized: `(streaming=on/off) × (guard=on/off) × (child_crash=on/off)`.

Assertions:

- Hard total deadline is enforced in all four cells.
- No silent unguarded fallback after child crash — degraded mode is recorded in metrics.
- Drafting-specific recovery fires uniformly across all cells.

Best target: `tests/test_work_session.py` (existing `test_work_session.py:6894-6996` is the right neighborhood).

### E. Refusal classification

Fixture: synthetic Codex output containing `response.refusal.delta`.

Assertions:

- Refusal is distinguishable from transport error at the work-loop boundary.
- Blocker taxonomy records `model_returned_wait_with_no_reason`.
- Follow-status surfaces refusal as a policy outcome, not `model_error`.

Best target: `tests/test_codex_api.py` (if exists) and `tests/test_work_session.py`.

### F. Prompt budget regression

Measure characters in: full work context, explore handoff, tiny draft contract, recovery-retry prompt.

Assertion: tiny draft contract ≤ 3000 chars; recovery-retry prompt ≤ tiny draft contract.

Best target: `tests/test_work_session.py` — one dedicated budget test file is fine too.

**Do not ship any of steps 3, 4, 5, or 6 above without the corresponding harness.** The entire thesis of this synthesis is that structural changes need replayable regressions, not more prompt iteration.

---

## Freeze / defer list

While loop stabilization is in flight, explicitly freeze the following. Surface any pressure to change them as a signal that the stabilization work needs to finish first.

**Frozen (do not touch):**

- `src/mew/write_tools.py` exact-match semantics. The strictness is load-bearing; bugs are upstream.
- Paired `tests/**` + `src/mew/**` write discipline for mew-internal changes.
- The 90s THINK timeout on write-ready fast path. More timeout is not a fix; shorter contracts are.
- `build_work_write_ready_think_prompt()` wording changes. The prompt should be replaced by the tiny contract (step 3), not tuned further.
- Global `tasks.py`. The new `WorkTodo` is session-scoped and distinct; leave `tasks.py` alone.
- `compact_model_turns_for_prompt()` and related compaction heuristics. The recovery path is the issue, not the compaction.

**Deferred (revisit only after step 6 lands):**

- Sub-agent / coordinator product surface (Claude Code's marketplace, Codex's reviewer task isolation). Premature without the compiler.
- Deferred-tool discovery / ToolSearch-style gating. Mew's tool count does not require it yet.
- MCP, hooks, permission stack expansions. Executor invariants first.
- Streaming assistant-message tombstones. Copy the invariant (terminal records on interrupt) via step 7, not the literal transcript surface.
- Reasoning-effort promotion rules in `src/mew/reasoning_policy.py`. The `policy`/`recovery` keyword promotion is suspicious for loop-stabilization work, but changing it mid-flight confounds measurement. Revisit after recovery lane lands.
- New prompt heuristics for exploration. The explore half is stable enough relative to the drafting half; do not start tuning it now.

**Actively resisted:**

- "Just raise the timeout to 180s." It makes failures slower, not rarer.
- "Add one more cached-window fallback." Each fallback further weakens the exact-span invariant.
- "Let the model produce tool-call JSON directly in fast-path mode." That is the current design, and it is the source of both buckets.

---

## Risks and tradeoffs

**Risk: the compiler becomes a second write-tools implementation.**
Mitigation: `PatchDraftCompiler` produces IR and validated `new_content`; the actual file mutation still goes through `src/mew/write_tools.py`. Treat the compiler as a preflight that happens to compute the same diff the write tool would compute — never as a parallel writer.

**Risk: `WorkTodo` duplicates `plan_items`.**
Mitigation: keep roles distinct. `plan_items` is model-derived advisory state (unchanged). `WorkTodo` is runtime ledger with transitions backed by tool calls, not inference. A session can have several `plan_items` and exactly one in-progress `WorkTodo`.

**Risk: tiny draft contract is too rigid; model refuses or misformats.**
Mitigation: that is already a failure mode today, just silent. The taxonomy makes it visible and gives recovery a well-defined next move. Add `model_returned_non_schema` as a first-class blocker and budget one bounded retry; escalate to a wider prompt only on second failure.

**Risk: validator is too strict and rejects legitimate drafts.**
Mitigation: the blocker codes are specific enough to classify each rejection. Any unexpected rejection produces a scenario that can be added to the harness. Strictness is a feature — today's leniency is exactly what produces silent regression.

**Risk: `WorkTodo` state races with existing recovery planner.**
Mitigation: step 4 is the single integration point. Until step 4, `WorkTodo` is advisory; once step 4 lands, recovery reads `WorkTodo` first and falls back to the existing planner only when no todo is in `drafting`.

**Risk: deferring executor lifecycle (step 7) leaves the explore half unstable.**
Accepted. The failure buckets named (`#399`, `#401`) are both on the drafting half. Step 7 is the right fix for explore stability, but sequencing it after drafting is deliberate — the drafting compiler is the higher-leverage change.

**Tradeoff: fewer prompt iterations during the stabilization window.**
Accepted. The synthesis is explicit that prompt tuning has diminishing returns here. Fluent model behavior is not the bottleneck; contract-level stability is.

**Tradeoff: more session-scoped state to persist and test.**
Accepted. This is the structural debt the audits identify. Paying it down is the task.

**Tradeoff: replay harnesses are not "free" tests — they require capturing real fixtures.**
Accepted. The alternative is another quarter of prompt iteration with no regression fixtures for the exact buckets that are failing. Fixture capture should happen now while live examples of #399 and #401 are available.

---

Synthesis complete. The shortest accurate description of the change: **give mew a body between `edit_ready` and the write tool.** Today the loop asks the model to be that body; every audit independently concludes that is the wrong architectural line. The Patch Draft Compiler, the `WorkTodo` ledger, and a drafting-specific recovery lane move that line to where Codex and Claude Code both already put it — inside the runtime, not inside the prompt.
