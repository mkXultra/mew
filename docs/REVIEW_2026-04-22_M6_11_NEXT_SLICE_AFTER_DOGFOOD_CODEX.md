# M6.11 Next Slice After Dogfood — Codex

## Verdict

**B — implement `m6_11-drafting-recovery`.**

## Reasoning

- Repo state is clean at `HEAD 8303098`.
- `./mew dogfood --scenario m6_11-compiler-replay --json` passes, while `m6_11-refusal-separation` and `m6_11-drafting-recovery` both still return `not_implemented`.
- `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json` is still red because timeout concentration is high: `14` bundles total, dominant `work-loop-model-failure.request_timed_out`, share `0.5714285714285714`.
- The highest-value missing evidence is now the Phase 4 recovery claim: the repo already has blocked-on-patch resume/follow-status parity surfaces in `src/mew/work_session.py` and `src/mew/commands.py`, plus focused coverage in `tests/test_work_session.py`. Turning that into one deterministic dogfood scenario is the smallest honest step.
- **Not A:** refusal separation already has direct lower-level coverage in `src/mew/codex_api.py` and `tests/test_codex_api.py`, and current calibration shows `refusal_count=0`. Adding the dogfood scenario is useful, but it adds less close-gate signal than proving drafting recovery.
- **Not C:** there is calibration support, but no actual `bucket_tag` / batch-analysis implementation in `src/mew`; landing incidence instrumentation now widens into replay schema and reporting work before the deterministic dogfood matrix is filled in.

## Exact Bounded Scope

- Touch only `src/mew/dogfood.py` and `tests/test_dogfood.py` unless the scenario exposes a real parity bug.
- Implement `run_m6_11_drafting_recovery_scenario(...)` as a deterministic local harness that:
  - creates a minimal blocked-on-patch session plus follow snapshot,
  - exercises the existing resume and `work --follow-status --json` surfaces,
  - asserts the same `phase=blocked_on_patch`, `blocker_code`, and `next_recovery_action` for the same `WorkTodo`,
  - asserts `resume_source=session_overlay` when the live session is richer.
- Keep `m6_11-refusal-separation` and incidence instrumentation deferred in this slice.
- Do not touch runtime drafting, prompt, replay-schema, or batch-analysis code here.

## Suggested Validations

- `uv run pytest -q tests/test_dogfood.py -k m6_11`
- `./mew dogfood --scenario m6_11-drafting-recovery --json`
- Add or update the aggregate dogfood expectation so the `m6_11-*` subset is pinned as `2 pass + 3 not_implemented`, not a misleading all-green claim.
