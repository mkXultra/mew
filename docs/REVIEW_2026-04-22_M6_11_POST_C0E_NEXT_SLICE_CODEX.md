# Recommendation

Choose one bounded slice: **pairing-aware preclassification for the tiny write-ready lane**.

# Why This Slice

- `c0eba4c` proved the latest tiny-lane failures are real 30s budget burns, not missing attribution: turn `1825` hit `tiny_write_ready_draft_elapsed_seconds=30.017...`, `timeout_budget_utilization≈1.0006`, `exit_stage=model_exception`, and `patch_draft_compiler_ran=false`.
- Another prompt-only shrink is unlikely to be the best next move. The tiny contract is already structurally minimal; the remaining bulk is mostly cached window text.
- A pure budget increase is the wrong direction. The lane is already consuming essentially the full `30s`; raising it would mostly lengthen stalls before proving the lane can return useful artifacts.
- The live sample also exposes one deterministic impossible path we can remove before the model call: turns `1822` and `1824` both compiled to the same blocker, `unpaired_source_edit_blocked` on `src/mew/cli.py` with recovery `add_paired_test_edit`.

# Exact Bounded Change

Touch `src/mew/work_loop.py` and `tests/test_work_session.py` only.

Implement a **pairing-aware tiny-lane filter/short-circuit** before `build_write_ready_tiny_draft_model_context()` / `build_work_write_ready_tiny_draft_prompt()` run:

- Derive the tiny-lane candidate paths from the current actionable surface, but remove any `src/mew/**` path that cannot be legally drafted on this turn because its paired `tests/**` surface is not present in the same tiny-lane target-path/cached-window set.
- Reuse the same pairing resolution mew already uses for source/test steering; do not invent a second pairing rule just for the tiny lane.
- If at least one legal paired slice remains, build the tiny context from only that reduced slice.
- If no legal paired slice remains, skip the tiny model call entirely and return the stable blocker path immediately (`unpaired_source_edit_blocked` / `add_paired_test_edit`), with a tiny-lane metric showing deterministic preclassification rather than timeout.

For the current `#402` shape, this should keep the `commands.py` + `tests/test_memory.py` slice and stop feeding the impossible `src/mew/cli.py`-without-paired-test surface into the 30s tiny call.

# Why Not The Other Options

- `more aggressive tiny prompt-contract shrink`: lower value next. The prompt contract is already stripped down; the stronger win is to stop sending impossible surfaces at all.
- `budget change`: reject for now. The new observability shows the lane is genuinely spending the whole budget.
- `blocker-stop only after compiler`: too late as the next slice. It helps the minority blocker path but does nothing for the dominant timeout share.

# Acceptance Criteria

1. On a `#402`-shape replay fixture, the tiny-lane target paths/cached windows exclude `src/mew/cli.py` unless its paired test surface is also present.
2. If the actionable tiny surface contains no pairable `src/mew/**` edit slice, the tiny model call is skipped and the turn records a deterministic blocker instead of a `30s` timeout fallback.
3. `tiny_write_ready_draft_prompt_chars` drops materially on the current three-window shape because impossible paths no longer enter the tiny context.
4. Non-write-ready turns and the generic fallback path remain unchanged.
