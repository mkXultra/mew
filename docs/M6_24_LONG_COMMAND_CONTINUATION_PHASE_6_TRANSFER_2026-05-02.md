# M6.24 Long-Command Continuation Phase 6 Transfer Closeout

Date: 2026-05-02

Status: transfer gate closed; same-shape `compile-compcert` speed_1 pending.

## Scope

This closes the transfer gate for
`docs/DESIGN_2026-05-02_M6_24_LONG_COMMAND_CONTINUATION.md` after the reviewed
Phase 4/5 budget/rendering and Harbor timeout-shape slice.

The purpose is to avoid spending another `compile-compcert` proof from a
CompCert-only repair. Phase 6 requires generic long-build coverage before the
same-shape speed rerun.

## Gate Evidence

Phase 6 close gate:

- at least two non-CompCert long-build transfer fixtures pass;
- acceptance still rejects nonterminal proof;
- scoped ruff and `git diff --check` pass;
- only then spend one same-shape `compile-compcert` speed_1.

Local transfer evidence:

- `WidgetCLI` ordinary CLI/source-build fixtures pass.
- `BarVM` default-runtime/runtime-link transfer fixtures pass.
- invalid target-surface and runtime-repair transfer fixtures pass.
- masked/spoofed artifact proof fixtures pass.
- `test_nonterminal_or_non_success_command_evidence_cannot_prove_artifact`
  keeps running/yielded/killed/timed-out command evidence from satisfying final
  artifact proof.

## Verification

Commands run:

```text
uv run pytest --no-testmon tests/test_long_build_substrate.py -q -k 'WidgetCLI or BarVM or non_compcert or default_runtime or masked_or_spoofed or invalid_target or runtime_repair'
uv run pytest --no-testmon tests/test_work_session.py tests/test_long_build_substrate.py tests/test_acceptance.py tests/test_harbor_terminal_bench_agent.py tests/test_toolbox.py -q
uv run ruff check .
python3 -c 'import json,pathlib; p=pathlib.Path("proof-artifacts/m6_24_gap_ledger.jsonl"); lines=[l for l in p.read_text().splitlines() if l.strip()]; [json.loads(l) for l in lines]; print(len(lines))'
git diff --check
```

Results:

- transfer subset: `29 passed`
- broader local suite: `1290 passed`, `67 subtests passed`, one
  multiprocessing fork deprecation warning
- full ruff passed
- gap-ledger JSONL parse passed: `152` records
- diff check passed

## Decision

Phase 6 transfer is closed for this slice.

Next action:

```text
M6.24 -> long_dependency/toolchain gap -> long-command continuation Phase 6 closed -> one same-shape compile-compcert speed_1
```

Do not run `proof_5` yet. The next run is one speed rerun only. If it records
movement or pass under the normal selected timeout shape, update
`docs/M6_24_DECISION_LEDGER.md` and decide whether to repair again or escalate.
