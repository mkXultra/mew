# M6.24 Repair Dossier Index

Purpose: provide a compact navigation surface for M6.24 repair history so
context compression and long sessions do not pick the next repair from only the
latest failure.

Use this before designing any M6.24 repair after the second same-gap or same
task-shape cycle.

| Gap class | Dossier | Primary evidence tasks | Status | Next preflight |
|---|---|---|---|---|
| `long_dependency_toolchain_build_strategy_contract` | `docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md` | `compile-compcert`; future related family: `mcmc-sampling-stan`, `protein-assembly`, `adaptive-rejection-sampler` | active | Read the dossier before another `compile-compcert` or long-dependency prompt/profile repair. |
| `compact_model_inference_contract_failure` | pending | `gpt2-codegolf` | selected repair closed; future if repeats | Create a dossier if another model/checkpoint/tokenizer task enters a repeated repair loop. |
| `system_service_state_permission_contract` | pending | `git-multibranch` | selected repair closed | Create a dossier if another system-service task enters a repeated repair loop. |
| `hard_task_implementation_strategy_contract_retention` / runtime artifact family | pending | `make-doom-for-mips`, `make-mips-interpreter` | selected repairs closed / historical | Create a dossier before reopening the hard-runtime profile or adding more hard-task prompt guidance. |

## Operating Rule

- Gap dossier first; task-specific appendix only when a task has many cycles.
- A new repair proposal must cite one dossier row or explain why no dossier
  exists.
- A dossier is decision memory for classification and repair selection. It is
  not a backlog.
