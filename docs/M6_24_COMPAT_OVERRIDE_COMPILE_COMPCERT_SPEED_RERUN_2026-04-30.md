# M6.24 `compile-compcert` Compatibility Override Speed Rerun

Task: `compile-compcert`

Result root:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compat-override-compile-compcert-1attempt-20260430-0843/2026-04-30__08-43-13/result.json`

## Summary

- requested shape: `-k 1 -n 1`
- auth: `auth.plus.json` mounted as `/codex-auth/auth.json`
- reward: `1.0`
- runner errors: `0`
- wall runtime: `28m 4s`
- external verifier: `3 passed`

This is same-shape speed evidence that the v0.3 compatibility override ordering
repair did not regress `compile-compcert` and can produce a passing artifact.

## Evidence

Primary result:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compat-override-compile-compcert-1attempt-20260430-0843/2026-04-30__08-43-13/result.json
```

Agent report:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compat-override-compile-compcert-1attempt-20260430-0843/2026-04-30__08-43-13/compile-compcert__byFamU6/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json
```

Verifier:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compat-override-compile-compcert-1attempt-20260430-0843/2026-04-30__08-43-13/compile-compcert__byFamU6/verifier/test-stdout.txt
```

## Behavior Notes

The run surfaced the intended compatibility override path:

- it inspected configure help and the exact Coq version rejection;
- it found and tried `./configure -ignore-coq-version x86_64-linux`;
- after that path did not finish the artifact, it moved to a compatible OPAM
  Coq `8.16.1` path;
- it built `/tmp/CompCert/ccomp`, installed the runtime library, compiled a
  smoke C program, and the external verifier passed all three checks.

The long-dependency resume state still lists stale strategy blockers after the
successful finish. That is not a score blocker for this repair, but it remains a
future report-polish item if it begins to confuse task selection.

## Next Action

Escalate to resource-normalized proof for this same shape:

```text
compile-compcert -k 5 -n 1
```

Do not resume broad measurement before this proof or before a new structural
blocker is recorded and repaired.
