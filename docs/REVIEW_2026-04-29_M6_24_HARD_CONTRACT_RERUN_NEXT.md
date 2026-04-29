# REVIEW 2026-04-29 - M6.24 Hard Contract Rerun Next

Decision: `revise`, do not resume broad M6.24 measurement yet.

## Recommendation

The selected gap improved, but only qualitatively. The hard-task contract
capsule should be counted as `improved_score_unchanged`: reward stayed 0/5, but
the rerun no longer shows false stub completion. All five trial reports keep
`task_done=false`, preserve the hard implementation contract, and either wait
honestly on permissions or continue into real source/toolchain/VM repair.

Classify the next primary blocker as `VM-strategy`, not permission, budget, or
generic reasoning.

Permission is real in 2/5 trials and should be smoothed, but 3/5 trials found a
non-system `/tmp` toolchain route and still failed at VM startup/opcode/frame
behavior. Budget is also real because the three useful trials ended at 30 steps
with concrete next actions, but increasing steps without a better runtime
failure strategy would mostly buy more compile churn. The evidence is not a
pure reasoning failure: the contract, source inventory, exact verifier, and
no-surrogate constraints were retained.

## Evidence

- Aggregate rerun: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-hard-contract-make-doom-5attempts-20260429-1235/result.json` records 5 trials, 0 errors, mean 0.0, reward 0.0 for all trials.
- `make-doom-for-mips__FTthu68`: waited at step 7 because the next probe needed `/usr/bin` and apt metadata outside declared read roots.
- `make-doom-for-mips__CNxtyTB`: waited at step 13 because `apt-get install` would write outside declared write roots.
- `make-doom-for-mips__Tc7wA2s`: built an ELF32 little-endian MIPS executable from `doomgeneric_img.c`; `node vm.js` terminated at `PC=0x0`, executed only 60 instructions, and did not create `/tmp/frame.bmp`.
- `make-doom-for-mips__AU2XCVT`: reached a real artifact and exact `node vm.js`; it failed with `Unknown SPECIAL3 function: 0x3b` and no `/tmp/frame.bmp`.
- `make-doom-for-mips__4uQ7VQW`: built a real ELF, mapped `PC=0x45b0c4` to `.data`/loader-startup behavior, and failed with `Unknown opcode: 0x3f`; no `/tmp/frame.bmp`.
- External verifier common failure: `test_vm_execution` times out waiting for `/tmp/frame.bmp`, then frame existence/similarity checks fail because the file is missing.

## Smallest Repair

Add one generic hard-runtime verifier strategy slice inside the existing
implementation contract path.

When a hard implementation task has a real built artifact plus an exact
verifier failure from a VM, emulator, interpreter, simulator, or custom runtime
harness, mew should convert the failure into a typed `open_contract_gap` before
spending more steps:

- classify the failure as one of `loader_entry`, `abi_registers_stack`,
  `unsupported_opcode_instruction_set`, `syscall_runtime`, or `expected_artifact`
- preserve the exact failure signature: command, exit code, PC/opcode/stdout,
  expected artifact path, and whether the artifact was source-built
- force the next action to inspect the harness/runtime source and map the
  artifact with generic tools such as `readelf`, `nm`, `objdump`, and
  `addr2line` before another rebuild
- reserve final steps for the exact verifier plus artifact proof rather than
  ending immediately after another compile attempt

This is generic arbitrary-workspace behavior. It should not encode Doom or
Terminal-Bench specifics.

## Rerun Gate

After that repair, rerun the same shape: `make-doom-for-mips`, 5 attempts,
same harness/artifact policy. Accept the repair as improved only if the rerun
shows no stub completion, no ordinary package/toolchain permission wait, and at
least one trial gets past the current VM startup/opcode blocker or produces
`/tmp/frame.bmp`. A score increase is ideal, but the minimum evidence should be
a narrower VM/runtime failure with the contract still preserved.
