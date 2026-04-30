# M6.24 `compile-compcert` Artifact Proof Calibration Proof_5 Auth-Expired Run

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract -> instrumentation/report -> long_dependency_timed_out_artifact_proof_calibration proof_5 -> compile-compcert
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-artifact-proof-calibration-compile-compcert-5attempts-seq-20260430-2123/result.json
```

## Summary

- requested shape: `-k 5 -n 1`
- auth: `auth.plus.json` mounted as `/codex-auth/auth.json`
- frozen Codex target: `5/5`
- observed score: `1/5`
- runner errors: `0`
- Harbor mean: `0.200`
- pass@2 / pass@4 / pass@5: `0.400` / `0.800` / `1.000`
- total runtime: `1h 5m 59s`
- close-gate value: invalid as clean mew-core close evidence

## Classification

This run is dominated by auth expiration, not by a clean repeated
`compile-compcert` implementation-lane blocker.

`auth.plus.json` expired during the run:

```text
auth.plus.json expires at 2026-04-30T13:22:19Z
run started at 2026-04-30T12:23:40Z
run finished at 2026-04-30T13:29:40Z
```

Trial readout:

- `compile-compcert__UHtpFBJ`: reward `1.0`; external verifier passed, but the
  final model step still hit `HTTP 401 token_expired` after the useful work was
  complete.
- `compile-compcert__5ZaZzTt`: reward `0.0`; immediate `HTTP 401 token_expired`.
- `compile-compcert__GMq2uuV`: reward `0.0`; immediate `HTTP 401 token_expired`.
- `compile-compcert__b4GEuSC`: reward `0.0`; immediate `HTTP 401 token_expired`.
- `compile-compcert__VjLmjJF`: reward `0.0`; actual `wall_timeout` during
  `make -j"$(nproc)" ccomp`, with `/tmp/CompCert/ccomp` missing.

The single wall-time failure remains dossier evidence for long-build strategy,
but it is not enough to select another mew-core repair from this proof_5,
because four of five trials were invalidated by expired auth.

## Repair

The immediate repair is proof infrastructure, not a Terminal-Bench-specific
solver and not another long-dependency prompt patch:

- load refresh tokens from both legacy `auth.plus.json` shape and
  `~/.codex/auth.json` Codex shape;
- derive access-token expiry from JWT `exp` when no explicit `expires` field
  exists;
- proactively refresh expired/nearly-expired Codex OAuth tokens;
- retry once after `HTTP 401`;
- persist refreshed auth while preserving both auth-file shapes.

## Next

Run the same resource-normalized `compile-compcert` proof_5 again after the
auth-refresh repair, preferably with `~/.codex/auth.json` mounted as a directory
so refreshed tokens can be persisted safely. Broad measurement remains paused.
