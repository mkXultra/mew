# M6.11 Phase 2.5 — Write-Ready Prompt Reduction Review (Claude)

Date: 2026-04-22
Scope: uncommitted diff on `main`
- `src/mew/work_loop.py` (write-ready context builder, write-ready THINK prompt, draft prompt contract version bump)
- `tests/test_work_session.py` (write-ready context/prompt assertions, draft prompt contract version assertions, one new bounded-size test)

Focus areas requested by caller:
1. Output schema compatibility for `normalize_work_model_action` must remain identical.
2. Prompt reduction must actually narrow the write-ready context rather than cosmetically trim text.
3. Contract version bump to `v2` must be consistently surfaced in tests and runtime metrics.
4. No unintended behavior changes outside prompt content/version.

## TL;DR

All four focus areas are met. No active blocking findings. One low-severity watch item (W1) on schema/context coherence for the `working_memory` output field is recorded for Phase 3 follow-up, not for this slice.

---

## Focus area 1 — `normalize_work_model_action` output schema

**Status: PASS. No change to parser or schema.**

`normalize_work_model_action` is the function that parses and normalizes the model’s returned JSON action (not a context builder). Its definition at `src/mew/work_loop.py:1682` is untouched by this diff; the action schema string returned by `_work_action_schema_text()` at `src/mew/work_loop.py:1520-1567` is also untouched.

Verification:
- `git diff src/mew/work_loop.py` grepped for `normalize_work_model_action` / `_work_action_schema_text` / `WORK_MODEL_ACTIONS` yields zero matches; the diff is localized to `build_write_ready_work_model_context`, `build_work_write_ready_think_prompt`, the new helpers `_write_ready_prompt_target_paths` / `_write_ready_prompt_active_work_todo`, and the constant bump.
- The updated test at `tests/test_work_session.py:6225-6228` explicitly asserts the standard schema union string `"batch|inspect_dir|read_file|…|edit_file_hunks|finish|send_message|ask_user|remember|wait"` is still in the prompt, and `tests/test_work_session.py:6229-6230` guards against any future drift into a `patch_proposal` / `patch_blocker` variant. So the v2 prompt still asks the model for the same action union `normalize_work_model_action` expects.

The change affects only the *context* we feed the model, not the *output* we parse. Input-side change, output-side contract preserved.

## Focus area 2 — actual prompt narrowing vs. cosmetic trim

**Status: PASS. Substantive semantic reduction with a char-budget test guard.**

Fields dropped from the write-ready model context (compared to `src/mew/work_loop.py` pre-diff):
- `date` (top-level).
- `task` (`id`, `title`, `description` clipped to 240, `status`, `kind`).
- `work_session.id`, `work_session.status`.
- `work_session.resume.working_memory`.
- `work_session.resume.plan_item_observations` (only `plan_item[0]` string is re-extracted into `active_work_todo.source.plan_item`).
- `work_session.resume.target_path_cached_window_observations`.
- `work_session.resume.pending_steer`.
- `work_session.resume.next_action`.
- `work_session.resume.suggested_verify_command` (detailed object; only `.command` is coalesced into `active_work_todo.source.verify_command` / `focused_verify_command`).
- `work_session.resume.verification_confidence`.
- `work_session.resume.recent_decisions` (last-one compact form).
- `work_session.resume.notes` (last-two compact form).
- `work_session.recent_read_file_windows` (replaced by an explicitly projected schema on `write_ready_fast_path.cached_window_texts`).
- `capabilities` (only `allowed_read_roots` / `allowed_write_roots` resurface under `allowed_roots`).
- `guidance` (clipped to 500, now dropped entirely).

Fields projected / summarized into the new shape at `src/mew/work_loop.py:1487-1517`:
- `active_work_todo`: `{id, status, source:{plan_item, target_paths, verify_command}, attempts:{draft, review}, blocker:{code, recovery_action}}`. The helper `_write_ready_prompt_active_work_todo` at `src/mew/work_loop.py:1446-1484` coalesces from `resume.active_work_todo` with defensive `isinstance` guards; `target_paths` are deduped via `_work_paths_match` combining todo-source paths with `recent_windows` paths (`src/mew/work_loop.py:1427-1443`).
- `write_ready_fast_path.cached_window_texts`: projected dicts with exactly `path`, `line_start`, `line_end`, `tool_call_id`, `text` (strips any other fields that used to ride along via `recent_read_file_windows`).
- `allowed_roots`: `{read, write}` only.
- `focused_verify_command`: top-level convenience duplicate of `active_work_todo.source.verify_command`.

The narrowing is enforced two ways in tests:
- `tests/test_work_session.py:6231` — `assertLess(len(fast_prompt), len(prompt))` compares the v2 write-ready prompt against the general THINK prompt built from the same state.
- `tests/test_work_session.py:6233-6282` — new test `test_write_ready_prompt_v2_stays_bounded_for_two_cached_windows_fixture` locks absolute bounds via `_write_ready_draft_prompt_chars`: `static_chars ≤ 6000`, `dynamic_chars ≤ 3000`, `len(prompt) ≤ 9000`. The split uses the `"\nFocusedContext JSON:\n"` marker (defined at `src/mew/work_loop.py:660`, preserved in the new prompt at `src/mew/work_loop.py:1666`).

This is structural narrowing, not whitespace/clip-only trimming. The bound test catches regressions if anyone later reintroduces `resume.*` or `work_session.*` fan-out.

## Focus area 3 — `v2` contract version surfacing

**Status: PASS. Single source of truth, all callsites resolved to `v2`, no stale `v1`.**

Constant bump:
- `src/mew/work_loop.py:64` — `WORK_WRITE_READY_DRAFT_PROMPT_CONTRACT_VERSION = "v2"`.

Runtime propagation path:
- `src/mew/work_loop.py:2246` — the constant (not a literal) is written into `model_metrics["draft_prompt_contract_version"]` inside the write-ready metrics update block at `work_loop.py:2231-2255`.
- `src/mew/work_session.py:4548-4550` — lifted into `draft_state["draft_prompt_contract_version"]` from the latest draft metrics.
- `src/mew/work_session.py:5095` — surfaced on `resume`.
- `src/mew/commands.py:6603, 6850-6852` — surfaced in per-turn metrics and failure-context text output.
- `src/mew/work_replay.py:120, 183` — persisted into replay resume context and replay diffs.

No hard-coded `"v1"` or `"v2"` strings exist in src/; the constant is the only source. Grep: `draft_prompt_contract_version.*v1|v1.*draft_prompt_contract_version` inside `src/` returns zero matches.

Test updates (12 call-sites, all string-literal comparisons — expected):
- `tests/test_work_session.py:6916` — write-ready metrics assertion.
- `tests/test_work_session.py:7263, 7280, 7295` — draft-state builder fixture inputs + resume assertion.
- `tests/test_work_session.py:7408, 7449` — turn-window fixture inputs + resume assertion.
- `tests/test_work_session.py:22756, 22813, 22839` — failure-context fixture + JSON + text assertions (first cluster).
- `tests/test_work_session.py:22883, 22940, 22967` — failure-context fixture + JSON + text assertions (second cluster).

Grep for `"v1"` in `tests/test_work_session.py`: zero matches. Remaining `v1` mentions in the repo are in archival review docs under `docs/REVIEW_2026-04-22_M6_11_PHASE*`, which are documentation, not runtime.

## Focus area 4 — unintended behavior outside prompt content/version

**Status: PASS, with one low-severity watch item (W1).**

Verified non-impacts:
- `normalize_work_model_action` and helpers — untouched (Focus 1).
- `_work_action_schema_text` — untouched (Focus 1).
- `_work_write_ready_fast_path_state` / `_work_write_ready_fast_path_details` — untouched (`src/mew/work_loop.py:1133, 1209`). Recent-window sourcing, abort-on-truncation behavior, fallback to `_write_ready_recent_windows_from_target_paths` — all preserved.
- `_shadow_compile_patch_draft_for_write_ready_turn` — untouched (`src/mew/work_loop.py:1249+`). Still reads `resume.active_work_todo` or `session["active_work_todo"]` for target paths and falls back to `working_memory.target_paths` / `recent_windows`. This code path ran on the old context and still runs correctly now, because it reads from `session` / `resume` directly, not from the prompt context.
- Draft attempts counting, cached-window hashing, retry-same-prefix logic at `src/mew/work_loop.py:2237-2254` — untouched.
- Prompt marker `"\nFocusedContext JSON:\n"` used by `_write_ready_draft_prompt_chars` — preserved at `src/mew/work_loop.py:1666`, so static/dynamic char metrics continue to split correctly.
- No caller other than `build_work_write_ready_think_prompt` consumes the dict returned by `build_write_ready_work_model_context`; grep for `fast_context["work_session"]`, `fast_context["task"]`, `fast_context["capabilities"]`, `fast_context["guidance"]`, `fast_context["date"]` returns zero matches in `src/` and `tests/`. Dropping those keys therefore cannot break any downstream reader.

Prompt instruction deltas (behavioral narrowing, intentional — noted for completeness):
- v1: "Do not add read or search actions unless those cached texts are insufficient for exact old/new text." → v2 strengthens to "Do not add read, search, glob, git, shell, or verification actions on this fast path." (`work_loop.py:1661`). Wider prohibition, no `unless` escape.
- v1: "Do not broaden scope, roots, or verification." → v2: "Do not broaden scope, roots, or the focused verify command." and adds "Do not invent uncached old text and do not propose a partial sibling edit set." (`work_loop.py:1662, 1664`).
- v2 also references the new context keys: `active_work_todo.source.target_paths`, `allowed_roots.write`, `focused_verify_command`. These string references match the keys actually emitted by `build_write_ready_work_model_context`, so the instructions are consistent with the context the model sees.

### W1 (low-severity watch item, not a blocker)

The action output schema emitted inside the prompt (`_work_action_schema_text` at `src/mew/work_loop.py:1524`) still asks the model to return a `working_memory` object (`hypothesis`, `next_step`, `plan_items`, `target_paths`, `open_questions`, `last_verified_state`). The v2 write-ready context no longer carries the *prior* `resume.working_memory` into the prompt, so on a write-ready turn the model must reconstruct `working_memory` from only `active_work_todo` + cached window texts. Prior `hypothesis` / `open_questions` / `last_verified_state` are no longer visible, so the model-produced working memory on write-ready turns may shed subtlety that a non-write-ready turn would have preserved.

Why this is a watch item, not a finding:
- It is deliberate narrowing consistent with the slice's stated intent (prompt reduction to avoid the 40k+ timeout regime referenced in the new test comment).
- Downstream consumers of `working_memory` recover on the next non-write-ready turn, which still has full `resume` context.
- Phase 3 is already planned to replace the action schema on the write-ready fast path with a `patch_proposal|patch_blocker` variant (per review docs in `docs/REVIEW_2026-04-22_M6_11_PHASE3_NEXT_SLICE_*`), which would obviate the generic `working_memory` field on this path entirely.

Recommendation: leave as-is for Phase 2.5. Revisit if Phase 3 slides or if calibration shows working_memory degradation on subsequent reentry turns across a write-ready boundary.

---

## Summary

- Output schema: unchanged.
- Prompt narrowing: structural, guarded by an absolute char-budget test.
- `v2` surfacing: single constant, all 12 test assertions updated, zero stale `v1` in src/ or tests/.
- Behavior outside prompt content/version: no regressions. One low-severity watch item on write-ready `working_memory` output under the retained generic action schema — acceptable for this slice, revisit in Phase 3.

No active blocking findings.

---

## 2026-04-22 follow-up — live evidence on task #402

Live sample after the slice: `prompt_chars` ~42k → ~20k, `tool_context_chars` ~57k → ~32k; 100% of turns still report `work-loop-model-failure.request_timed_out`; `compiler_bundles` remains 0.

**Recommendation: land as bounded progress.** Abandoning would revert working code, drop the char-budget guardrail at `tests/test_work_session.py:6233-6282`, and erase the `v2` stamp that lets any next slice compare the pre- and post-reduction regimes on the same failure corpus. The main tradeoff is that landing alone does not improve the live failure rate — the next slice must be scoped to a different axis, not another prompt trim.

Why the live numbers do not invalidate the slice:
- The reduction hit its mechanical target (prompt char budget roughly halved, tool context chars down ~44%). The live failure rate staying flat at 100% `request_timed_out` is itself the strongest evidence that prompt size is not the bottleneck; if it were, even a partial move would show up in the rate, and it did not.
- `compiler_bundles = 0` is consistent with 100% THINK timeouts rather than being a separate regression: `_shadow_compile_patch_draft_for_write_ready_turn` at `src/mew/work_loop.py:1249+` only runs *after* the write-ready THINK produces an action, so an upstream timeout suppresses the shadow compiler for free. The signal to watch after the next fix is whether non-zero `compiler_bundles` start appearing, not whether prompt size drops further.
- The `WORK_WRITE_READY_FAST_PATH_MODEL_TIMEOUT_SECONDS = 90` budget at `src/mew/work_loop.py:63` combined with reasoning-mode THINK calls is a plausible alternative bottleneck; another is the latency of the model backend itself at the given reasoning effort. Either is orthogonal to the context shape this slice changed.

Landing caveats to surface in the commit / PR description (so the next slice is not mis-scoped as another prompt reduction):
- State explicitly that v2 hit its char-budget target but did not move the live timeout rate on task #402.
- Flag that the next investigation axis should be the THINK timeout budget vs. reasoning latency split, the shadow-compiler activation path, or the Phase 3 `patch_proposal|patch_blocker` minimal action schema — not a further trim of the v2 context shape.
- Keep the `v2` stamp as the calibration discriminator for whichever of those axes is picked up next.

This recommendation flips to "abandon" only if a follow-up slice would replace `build_write_ready_work_model_context` wholesale (e.g., Phase 3 adopting `patch_proposal|patch_blocker` with a different context object). Even then, the `v2` metric and char-budget test are cheap to carry forward rather than revert.
