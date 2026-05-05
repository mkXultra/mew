# M6.24 Software/Coding Scope

Date: 2026-05-03

Source: `https://www.tbench.ai/benchmarks/terminal-bench-2?categories=&tags=software-engineering,coding`

Decision: M6.24 focuses on the Terminal-Bench 2.0 tasks returned by the
`software-engineering,coding` filters. The filtered page shows 25 tasks. This
replaces the prior all-registry close scope for M6.24.

Why: mew's near-term product goal is a developer/task/coding execution shell.
The full Terminal-Bench registry is useful as future benchmark inventory, but
it mixes non-coding domains that blur implement-lane diagnosis. This scoped
cohort still exercises normal implementation, native builds, services,
polyglot work, data engineering, numeric coding, proof-like coding, and hard
runtime tasks.

Historical evidence rule: earlier M6.24 evidence from out-of-scope tasks remains
valid repair evidence. `compile-compcert` is now historical build-orchestration
evidence, not an active M6.24 close gate, unless a later roadmap milestone
explicitly promotes a BuildOrchestrationLane benchmark.

## Scoped Tasks

| Task | Primary use in M6.24 |
|---|---|
| `build-cython-ext` | native-extension build and packaging |
| `circuit-fibsqrt` | hard coding / reasoning |
| `cobol-modernization` | implementation / modernization |
| `distribution-search` | coding / data search |
| `feal-differential-cryptanalysis` | hard coding / security |
| `feal-linear-cryptanalysis` | hard coding / security |
| `fix-git` | git repair / repository state |
| `hf-model-inference` | model runtime / inference integration |
| `kv-store-grpc` | service implementation |
| `largest-eigenval` | numeric coding |
| `make-doom-for-mips` | build orchestration / cross-runtime |
| `make-mips-interpreter` | interpreter / hard runtime |
| `merge-diff-arc-agi-task` | data merge / task transformation |
| `openssl-selfsigned-cert` | system tooling |
| `polyglot-c-py` | polyglot C/Python implementation |
| `polyglot-rust-c` | polyglot Rust/C implementation |
| `prove-plus-comm` | proof-like coding |
| `pypi-server` | service/runtime packaging |
| `pytorch-model-cli` | ML runtime CLI |
| `pytorch-model-recovery` | ML runtime recovery |
| `raman-fitting` | numeric/data coding |
| `regex-chess` | hard coding / reasoning |
| `reshard-c4-data` | data engineering |
| `schemelike-metacircular-eval` | interpreter implementation |
| `write-compressor` | algorithm implementation |

## Controller Update

- Rebaseline M6.24 against only these 25 tasks.
- Current active rebaseline is `implement_v2`; use
  `docs/M6_24_IMPLEMENT_V2_REBASELINE_2026-05-06.md` for task queue state and
  v2 evidence.
- Compare mew against frozen Codex `0.121.0` / `gpt-5.5@openai` targets for the
  same 25 tasks and trial counts.
- Select the next improvement target from an in-scope task or a generic repair
  clearly induced by an in-scope task.
- Do not spend new M6.24 live proof budget on out-of-scope tasks unless the
  newest user decision explicitly changes the scope.

Next action after this scope change:

```text
M6.24 -> software/coding cohort scope -> build scoped cohort rebaseline -> select first below-target in-scope gap
```
