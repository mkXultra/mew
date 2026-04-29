# M6.24 Deferred Verify Cleanup Speed Rerun

Date: 2026-04-29

Controller chain:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> deferred_verify_runtime_artifact_cleanup_on_timeout -> speed_1 make-mips-interpreter`

## Run

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-defer-verify-cleanup-make-mips-interpreter-1attempt-20260429-1702/result.json`

Command shape:

- task: `terminal-bench/make-mips-interpreter`
- trials: `-k 1 -n 1`
- model: `gpt-5.5`
- wrapper: `mew_terminal_bench_agent:MewTerminalBenchAgent`
- max steps: 30
- result: `0/1`
- exceptions: 0
- total runtime: 18m 49s

## What Improved

The implementation run reached a very strong internal state:

- `mew work --oneshot` exited normally with `stop_reason=finish`.
- mew created `/app/vm.js`.
- exact `node vm.js` ran from `/app` and exited 0.
- the runtime stdout showed Doom Shareware boot and framebuffer initialization.
- the runtime saved `/tmp/frame.bmp` and `/tmp/frame_000001.bmp`.
- mew inspected both BMP files and validated 640x400 32bpp, expected size,
  nonzero pixels, and nontrivial pixel data.

The external verifier still failed only:

```text
Expected text not found in output
assert b'I_InitGraphics: DOOM screen size: w x h: 320 x 200' in stdout_content
```

Frame existence and image similarity passed.

## Diagnosis

Gap class:

`deferred_verify_runtime_artifact_cleanup_report_fallback_missing`

The previous cleanup repair did not fire because the final one-shot resume had
no `stale_runtime_artifact_risk`:

```json
{
  "work_exit_code": 0,
  "post_run_cleanup": {},
  "resume_risk": {},
  "stop_reason": "finish"
}
```

The stale artifact evidence was present in the work report steps instead:

- tool #16: exact `node vm.js` saved the frame;
- tool #17: inspected `/tmp/frame.bmp` and `/tmp/frame_000001.bmp`.

Because cleanup only read the resume risk, not the final work report, the stale
runtime artifacts survived into the external verifier.

## Repair

Implemented immediately after this speed rerun:

- `src/mew/commands.py`
  - one-shot cleanup now falls back to `work_report.steps[*].tool_call` when the
    resume has no `stale_runtime_artifact_risk`;
  - the fallback builds the same generic stale artifact risk from task text plus
    completed tool output;
  - cleanup still only runs for `--defer-verify` and only removes `/tmp/...`
    artifacts surfaced by the risk detector.
- `src/mew/acceptance.py` and `src/mew/work_session.py`
  - runtime artifact creation markers now include `saved /tmp/` and
    `exists size=`, covering outputs such as
    `frame 1 saved /tmp/frame_000001.bmp` and
    `/tmp/frame.bmp: exists size=1024054`.
- tests:
  - `tests/test_acceptance.py`
  - `tests/test_work_session.py`

Focused validation:

```sh
uv run pytest tests/test_acceptance.py -k 'stale_runtime_artifact or runtime_command_pass_without_artifact' --no-testmon -q
uv run pytest tests/test_work_session.py -k 'stale_runtime_artifact or final_verifier_state_transfer or oneshot_cleanup' --no-testmon -q
uv run ruff check src/mew/acceptance.py src/mew/work_session.py src/mew/commands.py tests/test_acceptance.py tests/test_work_session.py
```

Observed:

- `4 passed, 49 deselected`
- `7 passed, 769 deselected`
- `ruff`: all checks passed

## GitHub Issues

Open side-project issues #25, #26, and #27 were checked after this rerun. They
remain useful implementation-lane hardening inputs, but each is already routed
as M6.16-style polish evidence and does not block this M6.24 same-shape repair:

- #25: verifier-green patch can fail to materialize after closeout timeout;
- #26: paired source/test hunk patch lacks a clean single tool shape;
- #27: near-complete verifier rollback patch should be easier to preserve.

The immediate repair remains the M6.24 stale runtime artifact handoff issue
observed in this same-shape trial.

## Next Rerun

Run another `speed_1` same-shape rerun for `make-mips-interpreter`.

Accept as materially improved if:

- `post_run_cleanup.kind` is `deferred_verify_runtime_artifact_cleanup` after a
  self-verifier leaves `/tmp/frame.bmp` or a frame copy;
- the external verifier no longer fails because a stale frame pre-exists;
- reward improves, or the failure moves to a new concrete runtime/verification
  condition.

Do not escalate to `-k 5 -n 5` unless this speed rerun passes or shows material
improvement that needs stability proof.

## Report-Step Fallback Rerun

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-report-step-cleanup-make-mips-interpreter-1attempt-20260429-1727/result.json`

Command shape:

- task: `terminal-bench/make-mips-interpreter`
- trials: `-k 1 -n 1`
- model: `gpt-5.5`
- wrapper: `mew_terminal_bench_agent:MewTerminalBenchAgent`
- max steps: 30
- result: `1/1`
- exceptions: 0
- total runtime: 13m 22s

Observed mew report:

```json
{
  "work_exit_code": 0,
  "post_run_cleanup": {
    "artifacts": [
      {
        "artifact": "/tmp/frame-000001.bmp",
        "source_tool_call_id": 13,
        "status": "removed"
      }
    ],
    "kind": "deferred_verify_runtime_artifact_cleanup"
  },
  "stop_reason": "finish",
  "step_count": 9
}
```

Verifier result:

- reward: `1`
- `test_vm_execution`: passed
- `test_frame_bmp_exists`: passed
- `test_frame_bmp_similar_to_reference`: passed

Interpretation:

The v0.3 report-step cleanup fallback closed the selected stale-runtime
artifact handoff gap for one same-shape diagnostic trial. mew still performed
real source/runtime work: it implemented `vm.js`, ran exact `node vm.js`,
emitted the expected `I_InitGraphics` stdout, created valid frame artifacts,
removed a stale runtime frame before external verifier handoff, and passed the
fresh external verifier.

## Next Proof

Escalate to a five-trial same-shape proof for `make-mips-interpreter`.

Rationale:

- The speed rerun passed and directly exercised the selected repair.
- The frozen Codex target for `make-mips-interpreter` is `3/5`.
- `-k 5 -n 5` is now justified by
  `docs/M6_24_GAP_IMPROVEMENT_LOOP.md` as close/escalation proof, not as a
  default diagnostic rerun.

Accept this repair as stable enough to choose the next gap or resume broader
measurement if the five-trial proof reaches or exceeds the Codex target and
does not expose a new repeated structural blocker.
