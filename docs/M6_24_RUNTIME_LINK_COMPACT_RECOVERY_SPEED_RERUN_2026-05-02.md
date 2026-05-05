# M6.24 Runtime-Link Compact Recovery Speed Rerun - 2026-05-02

## Trigger

Same-shape `compile-compcert` speed rerun after the reviewed runtime-link
compact-recovery repair:

- Job:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-compact-recovery-compile-compcert-1attempt-20260502-2228`
- Trial: `compile-compcert__FwLEy2A`
- Harbor trials: `1`
- Runner errors: `0`
- Harbor mean reward: `1.0`
- Runtime: about `30m22s`
- Verifier checks: all `3` passed
- `mew-report.work_exit_code`: `1`
- `work_report.stop_reason`: `wall_timeout`

This is a useful external pass, but it is not a clean M6.24 closeout proof.

## Internal Closeout Gap

The internal work session ended with:

- `resume.long_build_state.status=blocked`
- `current_failure.failure_class=source_authority_unverified`
- `legacy_code=external_dependency_source_provenance_unverified`
- `source_authority=blocked`
- `target_built=blocked`
- `default_smoke=blocked`

The external verifier passed because `/tmp/CompCert/ccomp` and its runtime
library were present and functional by the end of the container run. The
internal reducer did not reach the same conclusion because the source
authority correlation failed before the runtime recovery prompt could remain
narrow.

## Cause

The run acquired the source archive at an absolute path:

`/tmp/compcert-fetch/compcert-v3.13.1.tar.gz`

Later readback commands changed into the archive parent directory and proved
the same archive with a relative path:

`compcert-v3.13.1.tar.gz`

The source-authority correlator only matched exact path strings across
acquisition/readback. That left `external_dependency_source_provenance_unverified`
active, so later runtime-recovery compact prompts could still carry source and
dependency baggage even after the task had moved to a runtime-link repair.

The run also showed a brittle final readback shape: a source archive member
probe for `common/Archi.v` failed before the command could run the final
default smoke internally. A future successful rerun should avoid spending the
runtime recovery window on extra source-member proof once source authority has
already been correlated.

## Repair

Generic reducer repair:

- Correlate an authoritative absolute archive acquisition with a later relative
  archive identity readback only when both the hash readback and archive-list
  readback execute from the authoritative archive parent directory.
- Keep absolute-path mismatches rejected.
- Reject parent-directory escape paths such as `../other/<same-basename>`.
- Invalidate cwd tracking on unmodeled cwd mutation (`pushd`, `popd`,
  `builtin cd`, `command cd`, `eval`, `source`, dot-source, variable-based cd,
  or control-flow cd) instead of preserving a previous parent cwd.
- Treat direct extraction with `tar -x ... -C <absolute source dir>
  --strip-components=1` as a completed source-root placement, equivalent to
  extract-then-move, when paired with archive validation.

This is not a CompCert-specific rule. It is a source archive identity rule for
normal shell workflows that fetch to an absolute cache path and later verify
from that cache directory.

## Validation

- Focused source-authority/readback subset:
  - `uv run pytest -q tests/test_long_build_substrate.py -k 'source_authority and readback' --no-testmon`
  - `35 passed, 231 deselected`
- Full long-build substrate:
  - `uv run pytest -q tests/test_long_build_substrate.py --no-testmon`
  - `266 passed`
- Broader long-build/work-session/acceptance subset:
  - `uv run pytest -q tests/test_long_build_substrate.py tests/test_work_session.py tests/test_acceptance.py -k 'source_authority or runtime_link or compact_recovery or long_build or default_smoke' --no-testmon`
  - `283 passed, 994 deselected`
- Scoped Ruff:
  - `uv run ruff check src/mew/long_build_substrate.py tests/test_long_build_substrate.py`
  - passed
- Gap ledger JSONL parse:
  - passed
- `git diff --check`:
  - passed
- codex-ultra review:
  - session `019de907-194c-7841-b84f-8f9f6e6f33d9`
  - final `STATUS: APPROVE` after hardening basename/cwd spoof cases.

## Next

Run exactly one same-shape `compile-compcert` speed_1. Do not run `proof_5` or
broad measurement before that rerun records either a clean internal closeout or
a newer narrower gap.
