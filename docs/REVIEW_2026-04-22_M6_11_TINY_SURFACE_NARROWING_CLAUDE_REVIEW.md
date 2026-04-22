# M6.11 Tiny Write-Ready Draft Surface Narrowing — Claude Review (rereview)

Scope: uncommitted diff on `main` at `2026-04-22`, rereviewed after a follow-up
patch that (a) narrows `active_work_todo.source.plan_item` to the first
actionable plan-item observation and (b) extends the regression test to assert
prompt-content narrowing (stale plan_item text absent, fresh observation text
present, stale path absent). Files in scope: `src/mew/work_loop.py`,
`tests/test_work_session.py`, `ROADMAP_STATUS.md`. Code not modified.

## Verdict

**Land it.** The follow-up tightens the slice in the right direction: the tiny
prompt is now internally consistent (the `plan_item` label now agrees with the
narrowed `target_paths` and `cached_window_texts`), and the test lock is now
on rendered prompt content, not just the intermediate context dict. All prior
non-blocking findings still hold as "acknowledge and move on"; the one
medium-severity edge case (Finding A, fallback-window intersection emptying
`cached_window_texts`) is unchanged and remains a pre-next-slice follow-up, not
a blocker. One new cosmetic finding (Finding F) on indentation in the dict
literal was introduced by the follow-up patch and is worth fixing before merge
but does not affect correctness.

## What changed since the prior review

Two follow-up edits landed on top of the original narrowing:

1. **`active_work_todo.source.plan_item` now prefers the first actionable
   observation's `plan_item`** (`src/mew/work_loop.py:1838-1845`):
   ```python
   actionable_plan_item = ""
   if plan_item_observations and isinstance(plan_item_observations[0], dict):
       actionable_plan_item = str(plan_item_observations[0].get("plan_item") or "").strip()
   if actionable_plan_item:
       active_todo_plan_item = actionable_plan_item
   else:
       active_todo_plan_item = str((active_work_todo.get("source") or {}).get("plan_item") or "")
   ```
   This is a **deliberate precedence inversion** versus the regular path (see
   Finding H). The regular path at `work_loop.py:1754` uses
   `source.plan_item or first_observation.plan_item` (source wins); the tiny
   path now uses `observation.plan_item or source.plan_item` (observation
   wins).
2. **Test extends three prompt-content assertions**
   (`tests/test_work_session.py:6320-6325`):
   - `tiny_context["active_work_todo"]["source"]["plan_item"] == "Pair commands.py and tests/test_memory.py edits"` — locks the narrowed label.
   - `"stale task-surface cleanup" not in tiny_prompt` — stale plan_item is
     not rendered into the prompt.
   - `"Pair commands.py and tests/test_memory.py edits" in tiny_prompt` —
     fresh plan_item is rendered.
   - `"src/mew/cli.py" not in tiny_prompt` — existing stale-path assertion.

I verified with a side-by-side of the same context: the regular builder still
emits `source.plan_item = "stale-source-item"` while the tiny builder emits
`"fresh-observation-item"`. The test fixture exercises this inversion
directly.

## Re-assessment of prior findings

| # | Severity | Still holds? | Change since prior review |
| --- | --- | --- | --- |
| A | Medium | Yes | Unchanged. Follow-up does not address the `_write_ready_recent_windows_from_target_paths` fallback case where `cached_window_texts` collapses to `[]`. Still the one follow-up worth scheduling. |
| B | Low | Yes | Unchanged. `_work_paths_match` suffix matching quirk still inherited by the filter. |
| C | Low | Yes | Unchanged. Helper still does not call `normalize_work_path`. |
| D | Low | Yes | Unchanged. `ROADMAP_STATUS.md:146-149` item-10 wrap is still 3-space indent. |
| E | Low | Partially addressed | Test coverage now locks plan_item narrowing and prompt-content (positive + negative). Gaps on Finding A's empty-intersection case and the helper's dead `target_path` fallback remain. Scope of E is strictly reduced. |

## New findings introduced by the follow-up

### Finding F (Low / cosmetic) — dict literal indentation regressed for `"source":` key

Where: `src/mew/work_loop.py:1876-1887`.

Reading the file directly:

```python
    return {
        "active_work_todo": {
            "id": active_work_todo.get("id"),
            "status": active_work_todo.get("status"),
        "source": {                                       # <-- 8-space indent
                "plan_item": active_todo_plan_item,       # <-- 16-space indent
                "target_paths": active_todo_target_paths,
                "verify_command": str(...).strip(),
            },
            "attempts": dict(active_work_todo.get("attempts") or {}),
            "blocker": dict(active_work_todo.get("blocker") or {}),
        },
```

The `"source":` key is indented at 8 spaces instead of 12 (siblings `"id"`,
`"status"`, `"attempts"`, `"blocker"` are at 12). The inner keys inside
`"source": { ... }` are at 16 spaces, inconsistent with the opening brace's
level. Python accepts any whitespace inside a dict literal, so this is
semantically identical to the prior correctly-indented version — I verified
via `ast.parse` and by building a context end-to-end — but it looks like an
unintentional editor slip.

Why: **Low.** Purely cosmetic; no functional or test impact. Will get flagged
by `ruff`/`black` if the repo runs them in CI, and is visible noise in any
future `git blame` of this block.

How to apply: restore 12-space indent on the `"source":` line and 16-space
indent on its inner keys (matching the pre-follow-up shape). One-line fix.

### Finding G (Very low) — `source.plan_item` fallback does not `.strip()`

Where: `src/mew/work_loop.py:1841-1845`.

```python
actionable_plan_item = str(plan_item_observations[0].get("plan_item") or "").strip()
if actionable_plan_item:
    active_todo_plan_item = actionable_plan_item
else:
    active_todo_plan_item = str((active_work_todo.get("source") or {}).get("plan_item") or "")
```

The actionable branch applies `.strip()`; the fallback branch does not. If
`active_work_todo.source.plan_item` has leading/trailing whitespace, the tiny
prompt will carry it while the regular path's `_write_ready_prompt_active_work_todo`
(`work_loop.py:1754`) will strip it. Cosmetic and unlikely in practice because
upstream producers emit already-trimmed strings.

Why: **Very low.** No observed impact.

How to apply: wrap the fallback with `.strip()` for symmetry, or ignore.

### Finding H (Low / semantic) — deliberate precedence inversion between regular and tiny lanes

Where: `src/mew/work_loop.py:1754` (regular) vs. `work_loop.py:1838-1845`
(tiny).

- Regular: `source.plan_item or first_observation.plan_item` (source wins).
- Tiny: `first_observation.plan_item or source.plan_item` (observation wins).

This is intentional: the tiny lane narrows to the first actionable
observation, so using the observation's label is consistent with also using
only its `cached_windows` paths. It makes the tiny prompt internally
consistent (label agrees with paths). But on the same turn, the two prompts
can describe the "active plan item" with different strings — demonstrated by
the sanity check I ran against a shared fixture.

Why: **Low.** Semantically correct and matches the slice's stated intent.
Worth documenting so a future reader does not assume the divergence is a
bug.

Downstream impact: the `plan_item` string is prompt-only — `normalize_work_model_action`,
`compile_patch_draft`, and the preview translator do not read it. The shadow
compiler replay bundle is built from `proposal` + environment, not from the
tiny model context, so no leak. Only the model's text sees the divergence.

How to apply: add a one-line inline note (e.g. `# tiny lane prefers
first_observation.plan_item to match narrowed cached_windows`) or a short
mention in a follow-up ROADMAP entry. No code change required.

## Answers to the five review questions (updated)

### (1) Does it preserve generic/write-ready behavior outside the tiny lane? — **Yes**

All changes remain confined to `build_write_ready_tiny_draft_model_context`
and the new `_write_ready_tiny_draft_observation_target_paths` helper.
`build_write_ready_work_model_context`, `_write_ready_prompt_active_work_todo`,
and `_write_ready_prompt_target_paths` are untouched. All 12
`write_ready`-tagged tests still pass, including
`test_write_ready_prompt_v2_stays_bounded_for_two_cached_windows_fixture`
which pins the regular write-ready prompt envelope. The 3 tiny-draft tests
also pass.

### (2) Correctly prefers the first actionable plan-item surface without breaking fallback? — **Yes, now more thoroughly**

Preference now covers three fields consistently drawn from
`plan_item_observations[0]`:

- `target_paths` — from `cached_windows[i].path`.
- `cached_window_texts` — `recent_windows` filtered to those same paths.
- `plan_item` — from `observations[0].plan_item` (new in this follow-up).

Fallback to `source.plan_item` is correctly gated on
`actionable_plan_item` being non-empty after `.strip()`. When no observation
exists or its `plan_item` is empty, the tiny lane degrades to the pre-slice
source.plan_item text.

The helper's internal `target_path` fallback (`work_loop.py:1784-1789`) and
the outer `fast_path.cached_paths` fallback (`work_loop.py:1834-1835`) are
still effectively dead code under the coarse gate (`_work_write_ready_fast_path_state`
requires ≥ 2 well-formed `cached_windows` paths). Belt-and-suspenders but
never live on real turns.

### (3) Path-matching / stale-window / target-path edge cases — **Finding A still the only medium concern**

Unchanged from prior review. Summary:

| Case | Severity | Status |
| --- | --- | --- |
| `_write_ready_recent_windows_from_target_paths` fallback paths don't overlap with observation paths → empty `cached_window_texts` | **Medium (A)** | Not addressed; still the priority follow-up |
| `_work_paths_match` suffix ambiguity | Low (B) | Pre-existing |
| No `normalize_work_path` in helper | Low (C) | Pre-existing |
| Observation loses test/source invariant | Low (D, now subsumed) | Unreachable under gate |

### (4) Tests sufficient and correctly scoped? — **Coverage materially improved**

The follow-up strengthens the test in the ways that matter most for this
slice:

- **Prompt-content assertions** — the previous review flagged that the test
  only checked the intermediate `tiny_context` dict, not the final rendered
  prompt. Three new string assertions now close that gap:
  - Positive: fresh plan_item text in prompt.
  - Negative: stale plan_item text absent.
  - Negative: stale path absent (was already present).
- **Plan-item narrowing locked at context level** via
  `source["plan_item"]` equality.

Remaining gaps (unchanged from prior review):
- No test for Finding A's empty-intersection case.
- No test for the helper's dead-code fallback branches (acceptable, since they
  are unreachable under live gates).
- No test that the precedence inversion (Finding H) is the intended behavior
  across both lanes on the same fixture. Would be worth one side-by-side
  comparison test, but not required to land.

### (5) Should this land now as bounded M6.11 progress? — **Yes, more confidently than before**

- The follow-up makes the tiny prompt internally consistent. Pre-follow-up,
  the rendered tiny prompt could still say "plan_item: stale task-surface
  cleanup" while pointing at `commands.py` + `test_memory.py` — a cognitive
  trap for a model trying to reconcile the label against the paths. The
  follow-up removes that.
- Tests now lock the intended prompt content, which is the durable contract.
- Diff remains narrow and locally reviewable.
- No phase-boundary movement; ROADMAP update is still a scoped addendum to
  item 10.
- Finding F (cosmetic indent) is worth fixing before the commit is pushed
  but is not a landing blocker.

## Residual non-findings (acknowledged, not flagged)

- **Precedence inversion downstream impact is nil.** Verified that the
  `plan_item` string is consumed only by the tiny prompt rendering; the
  shadow compiler, previews, and paired-write batch normalizer do not read
  it.
- **Follow-up does not touch the tiny prompt builder** itself
  (`build_work_write_ready_tiny_draft_prompt`, `work_loop.py:2042-2063`) —
  narrowing still happens entirely at context-build time, which is the
  correct seam.
- **Prompt envelope.** Prior review noted that tiny prompt was ~18k chars on
  live turn 1822. This follow-up may shrink it further on turns where
  `source.plan_item` was verbose (e.g. multi-line todo descriptions); even
  if not, the narrowed label is no longer longer than the observation
  string. `tiny_write_ready_draft_prompt_chars` will observe either delta in
  calibration.
- **Test fixture realism.** The new fixture exercises exactly the
  `source.plan_item = "stale..."` vs. `observation.plan_item = "Pair..."`
  divergence that motivated the follow-up. Strong regression lock.

## Landing recommendation

**Land the slice.** The follow-up correctly completes the surface-narrowing
intent and strengthens the test contract. Pre-merge nit: fix the 8/16-space
dict-literal indent at `work_loop.py:1876-1887` (Finding F). Post-merge
follow-up queue, unchanged from prior review:

1. Finding A: decide whether empty-filter-result should preserve pre-slice
   `recent_windows` or emit a dedicated `tiny_write_ready_draft_fallback_reason`;
   add one test.
2. Optional: 4-space indent restoration on `ROADMAP_STATUS.md:146-149`.
3. Optional: inline note or roadmap line documenting the intentional
   precedence inversion (Finding H).
4. Calibration watch: confirm in live #402 that `tiny_write_ready_draft_prompt_chars`
   drops on previously-stale turns and that `compiler_*` fallback rates do
   not spike.

Nothing in the current diff blocks landing as bounded M6.11 progress.
