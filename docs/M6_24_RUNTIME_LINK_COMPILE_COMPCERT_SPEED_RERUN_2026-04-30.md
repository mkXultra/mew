# M6.24 `compile-compcert` Runtime Link Speed Rerun

Task: `compile-compcert`

Result root:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-compile-compcert-1attempt-20260430-1050/2026-04-30__10-49-08/result.json`

## Summary

- requested shape: `-k 1 -n 1`
- auth: `auth.plus.json` mounted as `/codex-auth/auth.json`
- reward: `1.0`
- runner errors: `0`
- wall runtime: `22m 3s`
- external verifier: `3 passed`

This is same-shape speed evidence that the v0.4 runtime link library repair did
not regress `compile-compcert` and can produce a fully functional compiler
artifact.

## Evidence

Primary result:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-compile-compcert-1attempt-20260430-1050/2026-04-30__10-49-08/result.json
```

Agent report:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-compile-compcert-1attempt-20260430-1050/2026-04-30__10-49-08/compile-compcert__dHLBSPJ/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json
```

Verifier:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-compile-compcert-1attempt-20260430-1050/2026-04-30__10-49-08/compile-compcert__dHLBSPJ/verifier/test-stdout.txt
```

## Behavior Notes

The run followed the intended runtime-link proof path:

- it grounded CompCert `3.13` under `/tmp/CompCert`;
- it configured with `-ignore-coq-version` and external `MenhirLib`;
- it patched the bundled Flocq proof for Coq `8.18`;
- it built `ccomp`;
- it built and installed the runtime library under the configured prefix;
- it verified `/tmp/CompCert/ccomp` by compiling, linking, and running a C
  smoke program;
- the external verifier passed all three checks, including the prior failing
  `-lcompcert` link path.

The earlier attempt at
`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-compile-compcert-1attempt-20260430-1024`
left a completed `mew-report.json` but no Harbor `result.json` or verifier
artifact after the parent process disappeared. It is not score evidence.

## Next Action

Escalate to resource-normalized proof for this same shape:

```text
compile-compcert -k 5 -n 1
```

Do not resume broad measurement before this proof or before a new structural
blocker is recorded and repaired.
