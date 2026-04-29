# M6.24 Runtime-Freshness Rerun - 2026-04-29

Controller chain:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> runtime_artifact_cleanup_external_verifier_alignment -> same-shape rerun`

## Run

Task:

`terminal-bench/make-doom-for-mips`

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-freshness-make-doom-5attempts-20260429-1425/result.json`

Run shape:

- model: `gpt-5.5`
- trials: `-k 5 -n 5`
- runtime: 30m 42s
- same task and same broad work-session path as the previous hard-runtime rerun
- same broad container read/write permissions as the previous rerun
- `--max-steps 30`

Result:

- `n_trials`: 5
- `n_errors`: 0
- `mean`: 0.000
- `pass@5`: 0.000
- reward `0.0`: all five trials

## Delta

The score stayed 0/5.

Positive movement:

- the previous stale `/tmp/frame.bmp` short-circuit was not reproduced
- every external verifier waited for a new `/tmp/frame.bmp` and failed because
  the artifact was absent, rather than because a stale artifact existed too
  early
- permission waits did not dominate the run
- all trials continued to work on real Doom/MIPS build, link, or VM/runtime
  paths rather than surrogate/stub completion

Negative movement:

- reward did not improve
- no trial left a final state that satisfied the external verifier
- three trials ended by wall/model timeout while still in runtime/build repair
- one trial failed by tool failure after reaching an ELF/VM execution blocker
- the best previous 2/3 external-verifier proximity was not preserved

Interpretation:

The runtime artifact freshness repair removed the stale-artifact false
condition, but exposed the next blocker:

`hard_runtime_final_verifier_state_transfer`

For hard runtime tasks, mew can now preserve useful VM/build evidence, but it
does not reliably convert that evidence into a final deliverable state that a
fresh external verifier can reproduce. This is still an implementation-lane
hard-task profile issue, not a new authoritative lane.

## Trial Shapes

| Trial | Stop | External verifier | Signal |
|---|---|---|---|
| `make-doom-for-mips__FhhDVXS` | `tool_failed` | 0/3 | Built a MIPS ELF path, but exact `node vm.js` exited quickly with `PC=0x0`, no frame, and the report recorded GP/GOT/startup evidence. |
| `make-doom-for-mips__khYyf4C` | `wall_timeout` | 0/3 | Exact `node vm.js` reached Doom startup text, then exited at `R_InitSprites: Sprite TROO : A : 1 has two lumps mapped to it`; no frame. |
| `make-doom-for-mips__sgb8Jnx` | `model_error` | 0/3 | Report recorded `last verification passed exit=0: node vm.js`, but the final external verifier still saw no `/tmp/frame.bmp`; state transfer/final verifier alignment failed. |
| `make-doom-for-mips__oW5uZAc` | `wall_timeout` | 0/3 | Re-linked 82 MIPS objects but stopped on hard-float/libgcc/abicalls link mismatch; no verified ELF/frame. |
| `make-doom-for-mips__hMVFE8r` | `wall_timeout` | 0/3 | Exact VM run reached syscall and instruction-emulation blockers: unhandled syscalls `4353`/`4403` and unknown R-type `sync`; no frame. |

All five external verifier logs failed the same three tests:

- `test_vm_execution`: timeout waiting for `/tmp/frame.bmp`
- `test_frame_bmp_exists`: `/tmp/frame.bmp` absent
- `test_frame_bmp_similar_to_reference`: file not found

## Classification

Status: `improved_score_unchanged_next_repair_selected`.

The selected hard-task repair sequence remains useful, but the next repair
should not be another artifact-cleanup slice. The failure moved from stale
artifact freshness to final verifier state transfer and hard-runtime finish
criteria.

Next selected gap:

`hard_runtime_final_verifier_state_transfer`

Architecture fit:

- decision: `implementation_profile`
- authoritative lane: `tiny`
- helper lanes: none for v0

Reason:

The work still has one authoritative output: a coding patch / runtime artifact
state that passes the external verifier. A new lane would hide
implementation-lane weakness. The next repair should be a hard-task
implementation profile guard: finish only after a verifier-shaped final run
proves that the deliverable state survives the same fresh command shape the
external verifier will use, or after the report records a precise blocking VM
runtime gap without claiming completion.

## Next Action

Keep M6.24 in improvement phase.

Do not resume broad measurement yet.

Before adding another hard-task structural repair, record `hard_task profile v0`
for M6.24 so the scattered hard-task policies have one profile boundary:

- detection: hard implementation/runtime tasks such as MIPS/ELF/toolchain/VM
- effort policy: high reasoning and bounded evidence-preserving runtime probes
- reentry fields: implementation contract, runtime contract gap, final verifier
  state transfer, stale artifact risk
- finish gates: exact verifier-shaped command, no surrogate finish, fresh final
  artifact/state proof, or explicit blocked runtime gap
- helper-lane boundary: optional read-only deliberation later, no write-capable
  second planner in M6.24
- architecture decision: `implementation_profile`

Then implement the smallest generic repair for
`hard_runtime_final_verifier_state_transfer` and rerun
`make-doom-for-mips` same shape again.
