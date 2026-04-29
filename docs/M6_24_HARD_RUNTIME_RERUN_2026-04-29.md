# M6.24 Hard-Runtime Rerun - 2026-04-29

Controller chain:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> hard-runtime verifier strategy v0 -> same-shape rerun`

## Run

Task:

`terminal-bench/make-doom-for-mips`

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-hard-runtime-make-doom-5attempts-20260429-1317/result.json`

Run shape:

- model: `gpt-5.5`
- trials: `-k 5 -n 5`
- runtime: 30m 33s
- same task and same broad work-session path as the previous rerun
- generic container system-package read/write permissions were opened for
  `/usr`, `/lib`, `/bin`, `/sbin`, `/var`, and `/etc` to prevent package-manager
  approval waits from hiding the runtime-strategy signal

Result:

- `n_trials`: 5
- `n_errors`: 0
- `mean`: 0.000
- `pass@5`: 0.000
- reward `0.0`: all five trials

## Delta

The score stayed 0/5, but the failure shape moved again.

Positive movement:

- no ordinary package/toolchain permission wait dominated the run
- no surrogate/stub-only false completion dominated the run
- all trials pursued real Doom/MIPS build or VM/runtime routes
- one trial, `make-doom-for-mips__sBoEbdY`, reached a practical internal
  success state: built `/app/doomgeneric_mips`, ran exact `node vm.js`, observed
  Doom startup stdout, and verified `/tmp/frame.bmp` as a valid 640x400 32bpp
  BMP
- external verifier results also improved below the reward threshold:
  - `sBoEbdY`: 2/3 tests passed
  - `MkeKE3D`: 1/3 tests passed
  - `hGGJBrY`: 1/3 tests passed

Remaining miss:

- reward remained 0 because the external verifier still failed at least one
  test in every trial
- the best trial failed only `test_vm_execution`: expected
  `I_InitGraphics: DOOM screen size: w x h: 320 x 200` was not present in the
  verifier-captured stdout
- `sBoEbdY` left `/tmp/frame.bmp` behind after its own self-verification; the
  external verifier waits only until `/tmp/frame.bmp` exists, then waits one
  second and terminates `node vm.js`
- because the stale frame already existed before the verifier started its fresh
  process, the verifier terminated the process too early and captured stdout
  only through `I_Init: Setting up machine state.`

## Trial Shapes

| Trial | Stop | External verifier | Signal |
|---|---|---|---|
| `make-doom-for-mips__JWHW98z` | `wall_timeout` at 27 steps | 0/3 | Built toward real VM path but no fresh `/tmp/frame.bmp` for verifier. |
| `make-doom-for-mips__KunWasN` | `tool_failed` at 17 steps | 0/3 | Reached branch/delay-slot repair path, but no final frame. |
| `make-doom-for-mips__MkeKE3D` | `wall_timeout` at 21 steps | 1/3 | Produced a frame, but stdout did not reach graphics init and image similarity was 0.7339. |
| `make-doom-for-mips__hGGJBrY` | `wall_timeout` at 29 steps | 1/3 | Same practical shape as `MkeKE3D`: frame existed, but stdout/similarity failed. |
| `make-doom-for-mips__sBoEbdY` | `finish` at 24 steps | 2/3 | Self-verified exact VM run and valid frame; external verifier failed due stale `/tmp/frame.bmp` timing. |

## Classification

Status: `improved_score_unchanged`.

The selected hard-task strategy repair is still useful. The run got closer to
the target than the previous rerun, but the next blocker is no longer simply
"map VM opcode/runtime failure". The best evidence points to a generic
verifier-freshness contract problem:

`runtime_artifact_cleanup_external_verifier_alignment`

For long-running runtime tasks, self-verification can create expected artifacts
under `/tmp`. If those artifacts persist into the external verifier, verifier
tests that wait for artifact creation can terminate the fresh process too early.

This is a generic arbitrary-workspace issue. It is not specific to Doom or
Terminal-Bench:

- screenshots, frames, logs, sockets, pid files, and checkpoints can all become
  stale verifier artifacts
- a resident agent must distinguish "artifact was observed during my
  self-check" from "artifact should be present before external verification"
- when the final verifier is expected to create the artifact itself, cleanup is
  part of the acceptance contract

## Next Action

Keep M6.24 in improvement phase.

Do not resume broad measurement yet.

Recommended next bounded repair:

1. add generic runtime verifier artifact-freshness guidance to the work session
   path
2. when a self-check runs a final command that creates `/tmp/...` artifacts,
   preserve evidence in the report but clean stale runtime artifacts before
   `finish` unless the task explicitly requires them to be pre-existing final
   deliverables
3. make finish/reentry surface `stale_runtime_artifact_risk` when an expected
   `/tmp/...` artifact existed before the final verifier command or was left by
   self-verification
4. rerun `make-doom-for-mips` same shape again and require either score
   improvement or a written decision that the remaining failure is a new class

Close condition for this selected repair:

- no permission wait on normal package/toolchain discovery
- no surrogate/stub completion
- best trial no longer fails because a stale runtime artifact short-circuits the
  external verifier
- reward improves, or external verifier passes at least the previously failing
  stdout timing condition in the best trial
