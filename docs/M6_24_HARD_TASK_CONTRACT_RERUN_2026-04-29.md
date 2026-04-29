# M6.24 Hard-Task Contract Rerun - 2026-04-29

Controller chain:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> hard-task contract capsule v0 -> same-shape rerun`

## Run

Task:

`terminal-bench/make-doom-for-mips`

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-hard-contract-make-doom-5attempts-20260429-1235/result.json`

Result:

- `n_trials`: 5
- `n_errors`: 0
- `mean`: 0.000
- `pass@5`: 0.000
- reward `0.0`: all five trials
- runtime: 20m 3s

## Delta

The score did not improve, but the selected gap class did move:

- baseline Batch 3 generated small surrogate/stub MIPS programs or fake-ish
  frame outputs instead of building from the provided Doom source
- this rerun preserved `implementation_contract` in reports and did not finish
  with a false complete state
- three trials reached a real build/VM-repair route for `doomgeneric_mips`
- every external verifier failure converged on the same behavioral miss:
  `/tmp/frame.bmp` was not produced before timeout

This means the v0 contract capsule reduced surrogate completion, but it is not
yet sufficient for benchmark success.

## Trial Shapes

| Trial | Stop | Signal |
|---|---|---|
| `make-doom-for-mips__FTthu68` | `wait` at 7 steps | Read/search needed `/usr/bin` and apt metadata outside allowed read roots. |
| `make-doom-for-mips__CNxtyTB` | `wait` at 13 steps | `apt-get install` needed system writes outside allowed write roots. |
| `make-doom-for-mips__Tc7wA2s` | `remember` at 30 steps | Built ELF32 little-endian MIPS from Doom source, but `node vm.js` terminated at `PC=0x0`; no frame. |
| `make-doom-for-mips__AU2XCVT` | `max_steps` at 30 steps | Built and patched VM loader; exact `node vm.js` failed with unknown SPECIAL3 function and no frame. |
| `make-doom-for-mips__4uQ7VQW` | `remember` at 30 steps | Built real ELF, then mapped VM failure to `.data`/loader/startup behavior; no frame. |

External verifier common failure:

- `test_vm_execution`: timeout waiting for `/tmp/frame.bmp`
- `test_frame_bmp_exists`: missing `/tmp/frame.bmp`
- `test_frame_bmp_similar_to_reference`: cannot open missing frame

## Classification

Status: `improved_score_unchanged`.

The immediate selected gap is still implementation-lane hard-task parity, but
the next repair should not be another broad benchmark run. codex-ultra review in
`docs/REVIEW_2026-04-29_M6_24_HARD_CONTRACT_RERUN_NEXT.md` classifies the next
primary blocker as `VM-strategy`: when a hard task reaches a real built artifact
and an exact VM/emulator/interpreter verifier failure, mew should convert that
failure into a typed contract gap before spending more steps.

Two secondary amplifiers remain:

1. Hard implementation tasks can still run under a small-task budget/effort
   shape.
2. Ephemeral container implementation tasks need an explicit package-manager /
   system-tooling permission profile, otherwise valid build strategies stop at
   approval boundaries rather than reaching the verifier.

These are generic arbitrary-workspace `mew work` concerns. None should become a
Terminal-Bench-specific solver.

## Next Action

Do not resume broad M6.24 measurement yet.

Recommended next bounded repair:

1. add a generic hard-runtime verifier strategy slice that classifies failures
   as `loader_entry`, `abi_registers_stack`, `unsupported_opcode_instruction_set`,
   `syscall_runtime`, or `expected_artifact`
2. preserve exact PC/opcode/stdout/stderr/artifact signatures in the resume
3. steer the next action toward runtime source plus `readelf` / `nm` / `objdump`
   / `addr2line` mapping before another rebuild
4. keep the hard-task effort and container-system permission amplifiers visible
5. rerun the same shape again, starting with `make-doom-for-mips`

Close condition for this selected repair remains evidence-based:

- no surrogate/stub completion
- no permission wait on normal package/toolchain discovery
- at least one trial gets past the current VM startup/opcode blocker or writes
  `/tmp/frame.bmp`, or the score improves
