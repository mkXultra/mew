# DESIGN 2026-04-29 - M6.24 Hard Task Profile v0

Controller chain:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> hard_task profile v0 -> hard_runtime_final_verifier_state_transfer`

## Purpose

M6.24 has accumulated several hard-task repairs:

- hard-task implementation contract retention
- hard-runtime verifier strategy
- runtime artifact freshness
- architecture fit gate for resident lane/profile decisions

These are useful, but scattered. This profile records the shared boundary so
future hard-task repairs do not drift into a new lane, task-specific
Terminal-Bench solvers, or another prompt-only patch.

## Architecture Fit

Decision: `implementation_profile`.

Authoritative lane: `implementation/tiny`.

Helper lanes: none in v0.

The output is still one coding/runtime deliverable that must satisfy an
external verifier. Hardness changes the policy and evidence required inside the
implementation lane; it does not justify a second write-capable planner or a
new authoritative lane in M6.24.

## Detection

Treat a task as hard-task profile eligible when the task or active evidence
contains at least one of these surfaces:

- nontrivial cross-compilation, toolchain, ABI, runtime, emulator, VM, or
  interpreter work
- large source tree plus hidden/external verifier
- repeated model/tool wall-time pressure while preserving real implementation
  evidence
- verifier output involving PC/opcode/syscall/artifact/runtime state
- prior same-shape trials showing qualitative progress without reward

Do not use "hard" as a vague label. The report must name the concrete surface,
for example `mips_elf_vm_runtime`, `large_source_hidden_verifier`, or
`cross_toolchain_link_runtime`.

## Policy

Hard-task profile v0 adds these requirements to the implementation lane:

- use high reasoning effort where the backend supports it
- keep one stable task contract with acceptance criteria and source-grounding
  evidence
- preserve runtime/verifier evidence in working memory and reports
- prefer bounded probes that answer one concrete blocker over broad exploratory
  loops
- avoid surrogate finishes, visible-fixture-only validation, and nearby
  verifier substitutes
- if the blocker is structural and affects task policy, verifier authority,
  helper lanes, or loop shape, run the M6.24 Architecture Fit Gate before code
  changes

## Reentry Fields

A hard-task work report should make these fields recoverable:

- `implementation_contract`
- `verifier_failure_repair_agenda.runtime_contract_gap`
- `stale_runtime_artifact_risk`
- `final_verifier_state_transfer` or an equivalent next-action note when an
  internal check cannot be reproduced by the external verifier
- exact command / cwd / artifact paths for the final verifier-shaped run
- last known blocker with enough source/runtime coordinates to continue:
  PC, opcode, syscall, linker error, artifact path, or failing assertion

## Finish Gates

For `task_done=true`, the profile requires one of:

1. The exact verifier-shaped command succeeds from the final workspace state,
   with evidence preserved.
2. The required final artifact exists for the right reason and is not a stale
   self-check artifact that hides a fresh verifier failure.
3. The report explicitly stops as blocked, with the concrete runtime or source
   blocker recorded, and does not claim completion.

If an internal self-check passes but the external verifier later fails because
the workspace does not preserve that success, classify the next gap as
`hard_runtime_final_verifier_state_transfer`.

## Non-Goals

- no Terminal-Bench-specific solver logic
- no new authoritative lane for hard coding tasks
- no write-capable deliberation or memory-explorer agent in M6.24
- no broad concurrent executor work unless a later milestone explicitly
  selects it
- no broad measurement resume while the selected hard-task gap remains open

## Next Repair Boundary

The immediate M6.24 repair after the runtime-freshness rerun should address:

`hard_runtime_final_verifier_state_transfer`

Accept as improved only if the same-shape rerun shows one of:

- reward improvement
- external verifier reaches or exceeds the previous best 2/3 proximity without
  stale-artifact timing failure
- a clearer hard-runtime blocker is preserved in the final report without false
  completion, and the decision ledger explains why another repair is selected
