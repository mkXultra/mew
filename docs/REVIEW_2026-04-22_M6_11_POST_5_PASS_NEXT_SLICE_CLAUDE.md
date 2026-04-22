# M6.11 Post-5-Pass Next Slice — Claude

Context: HEAD is `eb89867` (`Land M6.11 phase4 regression proof`). All five
`m6_11-*` dogfood scenarios pass, but the Phase 2/3 calibration checkpoint
at `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration`
is still honestly red on `failure_mode_concentration_ok=False`
(dominant share `0.5714`, > `0.4`). The Codex review at
`docs/REVIEW_2026-04-22_M6_11_POST_5_PASS_NEXT_SLICE_CODEX.md` recommends
**Strengthen-Iter-B: replay-cohort tagging + current-head incidence
summary**. This is my independent check.

Earlier `NEXT_SLICE*` and `NEXT_AFTER_*` review docs in `docs/` are now
stale: they recommended `m6_11-drafting-recovery`, `m6_11-draft-timeout`,
`m6_11-refusal-separation`, and `m6_11-phase4-regression`, all of which
have already landed (`b4c1018`, `1f1b76f`, `60832b9`, `eb89867`).

## 1. Verdict

**Agree with Codex. Implement Strengthen-Iter-B next.** Extend the
replay bundle writers in `src/mew/work_replay.py` with cohort tagging
(`git_head`, a stable `bucket_tag`, and `blocker_code` when present),
and extend `src/mew/proof_summary.py --m6_11-phase2-calibration` so the
existing mixed-session-392 root can be summarized per cohort without
changing any thresholds.

Do **not** start the bounded 20-slice incidence gate yet. Do **not**
spend the next slice on another prompt / timeout tweak. Do **not**
change calibration thresholds or drop old bundles.

## 2. Why / Why Not

### Why Strengthen-Iter-B is the right slice

- `ROADMAP_STATUS.md` at lines 2018-2058 now honestly says all five
  `m6_11-*` dogfood scenarios pass, and `tests/test_dogfood.py:478-661`
  confirms that at the test level. Close-gate item (A) is green.
- Close-gate items (B) and (C) in
  `docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md` are still
  open, and the roadmap `Next action` block (line 2060-2070) already
  flags the bounded `#399/#401` incidence gate as the work that comes
  after dogfood green.
- But firing that incidence gate against the current replay root
  would produce a measurement that is not trustworthy. The only
  current root is
  `.mew/replays/work-loop/2026-04-22/session-392/`, and per-bundle
  inspection (turns 1819-1826 under `todo-no-todo-392/`, attempts 1-6
  under `todo-todo-392-1/`) shows **four distinct prompt-contract
  generations coexisting**:
  - `turn-1819, 1820`: `draft_prompt_contract_version=v1`, no tiny lane
  - `turn-1821`: `v2`, still no tiny lane
  - `turn-1822, 1823`: v2 outer + tiny contract `v1`, no exit stage
  - `turn-1824, 1825`: v2 outer + tiny `v2`, `exit_stage=None`/`model_exception`
  - `turn-1826`: v2 outer + tiny `v3`,
    `tiny_write_ready_draft_exit_stage=compiler_fallback`,
    `tiny_write_ready_draft_elapsed_seconds=11.58`
- Turn 1826 is especially important: the outer turn is still labelled
  `failure.code=request_timed_out` (because the surrounding think-level
  envelope did time out), but `tiny_write_ready_draft_outcome=fallback`
  with `exit_stage=compiler_fallback` at `~11.6s` means the tiny patch
  lane itself **did not time out** — it exited via the new blocker
  promotion. That one bundle tells a very different story from the older
  v1/v2 bundles, yet the calibration checker cannot distinguish them.
- `grep` confirms `git_head`, `bucket_tag`, and `cohort` are **not**
  currently persisted in `src/mew/work_replay.py` or
  `src/mew/proof_summary.py`. The only hit is an unrelated `git_head`
  in `src/mew/context_checkpoint.py`. So this is new instrumentation,
  not a rename.
- The slice is small: `src/mew/work_replay.py` is 275 lines total with
  two existing writers (`write_work_model_failure_replay`,
  `write_patch_draft_compiler_replay`) that both already assemble a
  metadata dict — adding stable cohort fields is additive and local.
  `src/mew/proof_summary.py:summarize_m6_11_replay_calibration` is a
  single function; adding a cohort breakout under an existing key (or
  a new `cohorts: {current_head: ..., legacy: ...}` section) without
  changing threshold math is a contained edit.
- It is the smallest honest move: after this lands, a fresh bounded
  rerun can tell us whether a real Phase 2.5 timeout-reduction fix is
  still needed, or whether the v1/v2 bundles are carrying the dominant
  share alone.

### Why not the alternatives

- **Not "start the 20-slice incidence gate now."** The baseline in
  `PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md` §3.2 is the
  pre-M6.11 / soft-stopped M6.7 candidate queue, and the measured
  batch must be attributable to a single HEAD. Today's root is neither
  pre-M6.11 clean nor current-HEAD clean.
- **Not "one more prompt / timeout / operator-surface tweak."**
  `grep` + the turn-1826 bundle show the tiny contract already shrunk
  from v1→v2→v3 and now exits via `compiler_fallback` at ~11.6s. More
  tuning without a clean cohort measurement is blind optimization.
- **Not "Phase 2.5 calibration slice immediately."** The
  `dominant_share=0.5714` number is real but is computed over a
  mixed-cohort root; we don't yet know it reflects current HEAD.
  Jumping to Phase 2.5 skips the question of whether HEAD is already
  meeting the gate.
- **Not "re-open follow-status / operator surface."** That path is
  already landed in `build_work_session_resume(...)` / `--follow-status`
  and has two claude-ultra + codex-ultra approvals on record. The
  remaining measurement problem is on the replay/summary side, not the
  resume surface.
- **Not "resume M6.9 or M6.10."** The close-gate proposal is still open
  for M6.11.

## 3. Exact Files To Touch

Narrow slice, additive only:

- `src/mew/work_replay.py`:
  - stamp both `write_work_model_failure_replay(...)` and
    `write_patch_draft_compiler_replay(...)` metadata with:
    - `git_head` (read once via `git rev-parse HEAD`, best-effort;
      empty string if not a git worktree)
    - `bucket_tag` derived from already-persisted cohort-discriminating
      fields — my recommendation is to prefer the derived form so the
      write path avoids a subprocess, e.g. for model-failure bundles
      `bucket_tag = f"contract={draft_prompt_contract_version}/tiny={tiny_write_ready_draft_prompt_contract_version}/exit={tiny_write_ready_draft_exit_stage}"`,
      and for compiler bundles a tag derived from
      `validator_result.code` + contract version already present in
      the todo. Keep `git_head` as the authoritative cohort key and
      `bucket_tag` as a readable human cohort label.
    - `blocker_code` when the bundle carries one: for model-failure
      bundles, read from `model_metrics.tiny_write_ready_draft_fallback_reason`
      + `patch_draft_compiler_artifact_kind`; for compiler bundles,
      read from `validator_result.code` (already accessed by
      `_read_validator_result_code` in proof_summary).
- `src/mew/proof_summary.py`:
  - extend `summarize_m6_11_replay_calibration(...)` with a
    `cohorts: {current_head: {...}, legacy: {...}, unknown: {...}}`
    section that carries the same
    `total_bundles / bundle_type_counts / dominant_bundle_share /
    thresholds` shape, computed per cohort.
  - **Do not** change the top-level threshold math. The top-level
    result continues to report the mixed view so the previous contract
    is preserved.
  - extend `format_proof_summary(...)` to print one extra line per
    cohort with the same shape as the existing
    `calibration_dominant_type` line.
- `tests/test_work_replay.py`:
  - add tests proving both writers persist `git_head`, `bucket_tag`,
    and `blocker_code` (when applicable) on the metadata payload.
  - use a small in-memory fixture for `git_head` failure (non-git dir)
    so the writer never raises.
- `tests/test_proof_summary.py`:
  - add tests proving the cohort breakout:
    - all-current-HEAD bundles produce `cohorts.current_head` matching
      the top-level numbers and `cohorts.legacy` empty
    - mixed roots (synthetic mix of two `git_head` values) split cleanly
    - bundles missing `git_head` / `bucket_tag` stay visible under
      `cohorts.unknown` and are **not** silently merged into
      `current_head`
    - threshold math for the current-head cohort matches the
      previously-top-level math

Do **not** touch `src/mew/work_loop.py`, `src/mew/work_session.py`,
`src/mew/patch_draft.py`, `src/mew/commands.py`, `src/mew/dogfood.py`,
or any `m6_11-*` dogfood fixture. The landed behavior on those
surfaces is already under claude-ultra + codex-ultra approval.

## 4. Focused Validation

- `uv run pytest -q tests/test_work_replay.py tests/test_proof_summary.py --no-testmon`
- `uv run pytest -q tests/test_dogfood.py -k m6_11 --no-testmon` — the
  five `m6_11-*` scenarios must still pass with the new fields present.
- `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration`
  on HEAD — confirm the existing overall numbers
  (`total_bundles=14`, dominant share `0.5714`,
  `failure_mode_concentration_ok=False`) are unchanged, and that the
  new cohort lines are emitted.
- `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json`
  — inspect `calibration.cohorts.current_head` vs
  `calibration.cohorts.legacy` directly; `current_head` should
  exclude `turn-1819, 1820` (v1 outer) and the early tiny-`v1` turns.
- Success condition for this slice: session-392 is attributable by
  cohort; a subsequent rerun against a cleaner HEAD can measure
  current-HEAD timeout concentration honestly without threshold
  changes or bundle deletion.

## 5. Main Risk

**Cohort key choice.** `git_head` is the cleanest authoritative cohort
identifier, but reading it at bundle-write time adds a `git rev-parse`
subprocess on every failure/replay capture. Two mitigations:

- Read `git_head` once per process (module-level cache) rather than
  per-bundle. This keeps write-path cost at ~1 subprocess per session.
- Make the read best-effort: empty string on any failure (non-git dir,
  detached worktree, permission error). Bundles without `git_head`
  still go to `cohorts.unknown`, never silently into `current_head`.

Secondary risk: the `bucket_tag` derivation keys off
`draft_prompt_contract_version` / `tiny_write_ready_draft_prompt_contract_version`
fields that live in `model_metrics` on model-failure bundles but are
not directly present on compiler bundles — the compiler bundle metadata
today only includes `session_id`, `todo_id`, `attempt`, `captured_at`,
and file pointers. For compiler bundles, the cohort key should be
derived from the persisted `validator_result.json` + `todo.json` file
contents (both already written alongside `replay_metadata.json`), or
the writer should be given the current `draft_prompt_contract_version`
so both bundle families share the same cohort taxonomy. Either choice
is fine; the important thing is to pick one and document it in the
tests so the cohort boundary is not implicit.

Tertiary risk: format drift. Changing `format_proof_summary(...)`
output adds one or more lines that downstream tooling may parse.
Keep the additions purely additive and place cohort lines **after**
the existing `malformed_bundle_types:` line so existing parsers
that read the first N lines stay stable.
