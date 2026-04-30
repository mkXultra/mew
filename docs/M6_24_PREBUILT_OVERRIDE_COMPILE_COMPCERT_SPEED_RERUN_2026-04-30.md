# M6.24 `compile-compcert` Prebuilt Override Speed Rerun

Task: `compile-compcert`

Result root:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-prebuilt-override-compile-compcert-1attempt-20260430-1211/2026-04-30__12-10-22/result.json`

## Summary

- requested shape: `-k 1 -n 1`
- auth: `auth.plus.json` mounted as `/codex-auth/auth.json`
- reward: `1.0`
- runner errors: `0`
- wall runtime: `14m 29s`
- external verifier: `3 passed`

This is same-shape speed evidence that the v0.5 prebuilt dependency override
precedence repair can produce a fully functional `ccomp` artifact without first
spending the budget on version-pinned source-built OPAM dependencies.

## Evidence

Primary result:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-prebuilt-override-compile-compcert-1attempt-20260430-1211/2026-04-30__12-10-22/result.json
```

Agent report:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-prebuilt-override-compile-compcert-1attempt-20260430-1211/2026-04-30__12-10-22/compile-compcert__wWch65f/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json
```

Verifier:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-prebuilt-override-compile-compcert-1attempt-20260430-1211/2026-04-30__12-10-22/compile-compcert__wWch65f/verifier/test-stdout.txt
```

## Behavior Notes

The run followed the intended prebuilt-dependency plus source-override path:

- it installed prebuilt distro OCaml/Coq/Flocq/Menhir dependencies;
- it fetched and grounded CompCert `3.13.1` source under `/tmp/CompCert`;
- it observed the Coq version mismatch and inspected configure help;
- it configured with `-ignore-coq-version`, `-use-external-Flocq`, and
  `-use-external-MenhirLib`;
- it ran `make depend`, then built the explicit `ccomp` target;
- it built and installed the runtime library;
- it verified `/tmp/CompCert/ccomp` by compiling, linking, and running a C
  smoke program;
- the external verifier passed all three checks.

Residual calibration signal: the final mew report still included stale
`long_dependency_build_state.missing_artifacts` entries after a successful
verifier pass. That is report/resume cleanup evidence, not a blocker for this
selected score repair unless it begins to affect next-action selection.

## Next Action

Escalate to resource-normalized proof for this same shape:

```text
compile-compcert -k 5 -n 1
```

Do not resume broad measurement before this proof or before a new structural
blocker is recorded and repaired.
