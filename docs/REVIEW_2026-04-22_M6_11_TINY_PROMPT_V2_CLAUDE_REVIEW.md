# M6.11 — Tiny write-ready draft prompt v2 (Claude review)

Reviewed uncommitted diff on `main` @ working-tree 2026-04-22:
`src/mew/work_loop.py`, `tests/test_work_session.py`, `ROADMAP_STATUS.md`.

## Verdict

**Land as-is.** Bounded, low-blast-radius Phase 3 slice that acts on the
live #402 timeout signal without widening scope beyond the tiny lane.

## What the slice actually changes

1. `build_write_ready_tiny_draft_model_context` drops, from both
   actionable-path and fallback branches (`work_loop.py:1846-1880`):
   - `active_work_todo.id`, `status`, `attempts`, `blocker`
   - `active_work_todo.source.verify_command`
   - `focused_verify_command` (top-level)
   - Per-window `line_start`, `line_end`, `tool_call_id`,
     `window_sha256`, `file_sha256`
   Kept: `source.plan_item`, `source.target_paths`,
   `cached_window_texts[].{path,text}`, `allowed_roots.write`,
   `write_ready_fast_path.{active,reason}`.
2. `build_work_write_ready_tiny_draft_prompt` serializes context with
   `separators=(',', ':')` instead of `indent=2` (`work_loop.py:2054`).
3. `WORK_WRITE_READY_TINY_DRAFT_PROMPT_CONTRACT_VERSION` bumped
   `v1 → v2` (`work_loop.py:66`).
4. New unit test `test_tiny_write_ready_draft_context_and_prompt_are_minimal_contract`
   pins the shape (+ compact form), plus a one-line `v2` assertion in the
   existing `tiny_write_ready_draft_*` integration fixture
   (`test_work_session.py:7140`).

## Answers to the review prompts

### 1. Does it preserve generic/write-ready behavior outside the tiny lane?

Yes. `build_write_ready_work_model_context` (`work_loop.py:1800-1822`) is
untouched and still emits `id/status/attempts/blocker/verify_command/
focused_verify_command/line_start/line_end/tool_call_id/window_sha256/
file_sha256` fields on the generic path. `build_work_write_ready_think_prompt`
(`work_loop.py:2014-2031`) still uses `json.dumps(..., indent=2)`. Only the
tiny lane builder and tiny prompt are affected. The `v2` namespace on the
non-tiny side (`WORK_WRITE_READY_DRAFT_PROMPT_CONTRACT_VERSION`) is unrelated
to the tiny constant — sharing the string doesn't collide because each
metric has a distinct key (`draft_prompt_contract_version` vs
`tiny_write_ready_draft_prompt_contract_version`).

### 2. Is the tiny context reduced only to load-bearing fields?

Mostly yes. The tiny prompt's output schema is `{kind, summary, files:
[{path, edits:[{old,new}]}], code, detail}` (`work_loop.py:2046-2053`) —
no line numbers, no hashes, no todo-id, no verify command appear in the
output. For the model to produce that schema it only needs:
- which paths are writable (`allowed_roots.write`, `target_paths`),
- what plan item this satisfies (`plan_item`, for a human-readable reason),
- the exact text it can cite as `old` (`cached_window_texts[].text`),
- which path each cached text belongs to (`cached_window_texts[].path`).

All four are preserved. The removed fields were either
model-invisible/auditing metadata (tool_call_id, window_sha256,
file_sha256, todo.id), or generic-lane fields irrelevant to patch drafting
(focused_verify_command, source.verify_command, attempts, status, blocker).

**Patch-correctness safety net:** the downstream patch-draft compiler
(`_compile_write_ready_patch_draft_proposal` →
`_write_ready_patch_draft_environment`, `work_loop.py:1312-1385`) derives
`cached_windows` **directly from `write_ready_fast_path.recent_windows`**,
not from `tiny_context.cached_window_texts`. It still sees
`line_start/line_end/window_sha256/file_sha256/context_truncated` unchanged
(`work_loop.py:1355-1366`) and still reads live files for exact-old-text
validation (`work_loop.py:1368-1380`). If the model fabricates `old` text
that doesn't match live_files, the compiler rejects with a stable code and
the lane falls back — the existing safety rail, unchanged.

### 3. Are the new tests sufficient and correctly scoped?

Sufficient for the contract:
- Pins the exact key set at three nesting levels (root, `active_work_todo`,
  `active_work_todo.source`, and per-window entries).
- Asserts the specific removed fields (`id/status/attempts/blocker/
  verify_command/focused_verify_command/line_start/line_end/tool_call_id/
  window_sha256/file_sha256`) are absent from both the context and from
  the emitted prompt's `FocusedContext JSON:` slice.
- Verifies the compact-serialization contract via
  `assertNotIn("\n", focused_context)` after splitting on the JSON marker —
  catches any regression to `indent=2`.
- Adds a `v2` version check on the integration-style fixture so bundles
  and the pre-model metrics sink will carry the new version.

Scoped correctly: the test uses `build_write_ready_tiny_draft_model_context`
and `build_work_write_ready_tiny_draft_prompt` directly, so it doesn't drag
in the model-call machinery.

**Nit (nice-to-have, not a blocker):** the existing bound test
`test_write_ready_prompt_v2_stays_bounded_for_two_cached_windows_fixture`
(`test_work_session.py:6449`) asserts upper bounds on the **non-tiny**
prompt only. Codex acceptance criterion #3 ("tiny_write_ready_draft_prompt_chars
drops materially from ~18040") is not locked in a unit test; it becomes
visible only on the next live #402 rerun. Adding a parallel
`assertLessEqual(len(tiny_prompt), <ceiling>)` fixture — say 9000 chars on
the two-window paired case — would prevent silent re-inflation from
future field additions. Propose as a follow-up, not a landing blocker.

### 4. Any subtle regressions or dead/unreachable branches?

None found. Specific checks:

- **Symmetry between branches:** the actionable-target-paths branch and
  the fallback branch (`work_loop.py:1846-1865`) drop exactly the same
  fields. No asymmetry, no dead enum values.
- **No orphaned readers:** grep confirms no code inside the tiny flow
  reads `tiny_context["active_work_todo"]["id"|"status"|"attempts"|
  "blocker"]`, `tiny_context[...]["source"]["verify_command"]`, or
  `tiny_context["focused_verify_command"]`. Those keys were only produced,
  never consumed outside the model prompt envelope.
- **Contract-version consumers:** `tiny_write_ready_draft_prompt_contract_version`
  is only surfaced into `model_metrics` and replay bundles; no code
  branches on its literal value, so bumping v1 → v2 is safe for replay
  consumers. (`grep` shows only emission sites, no `== "v1"` comparisons.)
- **Multi-window-same-path edge case:** if two non-adjacent windows ever
  survive the `actionable_target_paths` filter for the same path, the
  model loses `line_start/line_end` as a disambiguator. In practice this
  is rare — the filter is designed for paired src+test (one window per
  path) — and any incorrect `old` text will fail the compiler's exact
  match against live_files and fall back. Pre-existing safety rail
  handles it; no new failure mode.
- **`blocker` signal loss:** the tiny prompt no longer sees
  `active_work_todo.blocker`. If an earlier turn produced a stable
  patch_blocker, the tiny lane may re-propose the same failing shape.
  This is not a new regression — today's tiny caller does not gate on
  blocker state either; only the generic lane re-sees it on fallback. If
  timeout rate drops but a "same-blocker-replay" signal emerges in
  calibration, that's the next slice's concern (Claude's observability
  recommendation in `REVIEW_2026-04-22_M6_11_POST_E474_NEXT_SLICE_CLAUDE.md`).

### 5. Should this land now as bounded M6.11 progress?

Yes. Rationale:

- The live signal post-`e474b6a` is unambiguous: tiny-lane prompt envelope
  still ~18040 chars and the outcome is `timeout`. Narrowing which windows
  flow in didn't move the envelope; shrinking what the envelope carries per
  window is the next obvious lever.
- Blast radius is small: the tiny lane already has a complete fallback to
  the generic write-ready THINK path, so a quality regression in tiny
  outputs degrades gracefully rather than blocking the session.
- The slice is a clean prerequisite for the observability work recommended
  in the parallel review (`REVIEW_2026-04-22_M6_11_POST_E474_NEXT_SLICE_CLAUDE.md`):
  if shrink does not reduce timeout share on the next `#402` rerun,
  observability becomes the forced next slice and its `exit_stage`
  bucketing will be interpretable relative to a known-smaller envelope.
- Touches only `src/mew/work_loop.py`, `tests/test_work_session.py`, and
  a roadmap note. Stays inside M6.11 Phase 3 boundaries.

## Findings by severity

**No high-severity findings.**

**Medium:** none.

**Low / nit-level (non-blocking):**
1. No unit-level bound assertion on the tiny prompt length. Add a
   two-window paired fixture asserting `len(tiny_prompt) < ~9000` to lock
   the shrink against silent re-inflation. Follow-up, not a blocker.
2. `ROADMAP_STATUS.md` hunk also touches indentation on item 11
   (whitespace-only change unrelated to the shrink). Tolerable, but a
   clean split would have kept the shrink note isolated.

## Landing recommendation

Land this slice as one commit, e.g.
`Shrink M6.11 tiny write-ready draft prompt to v2`. Follow-through on the
next `#402` live rerun should answer two questions before picking the
next slice:
- Did `tiny_write_ready_draft_prompt_chars` drop materially (target:
  well under the 18040 baseline, ideally sub-10k on the two-window case)?
- Did `tiny_write_ready_draft_outcome=timeout` share fall from the current
  dominant ≥0.833?

If envelope dropped but timeout share didn't move, the next slice should
be the lane-specific elapsed observability work recommended in
`REVIEW_2026-04-22_M6_11_POST_E474_NEXT_SLICE_CLAUDE.md` — that will
disambiguate genuine model-latency timeouts from transport/guard-level
timeouts masquerading as such. If both dropped, the Phase 3 calibration
dominant-share gate is the next stop.
