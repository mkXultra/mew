# M6.24 Validated Archive Source Signal Speed Rerun

Date: 2026-05-02 JST

## Summary

Same-shape `compile-compcert` speed rerun after commit `2c56962`
failed externally and internally.

Job:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-validated-archive-source-signal-compile-compcert-1attempt-20260502-1000`

Trial:

`compile-compcert__BUjRG4Q`

Observed result:

- Harbor reward: `0.0`
- Runner errors: `0`
- Runtime: about `31m`
- Command transcript exit: `1`
- `mew-report.work_exit_code`: `1`
- External verifier: all three checks failed because `/tmp/CompCert/ccomp` did not exist
- Long-build state: `source_authority=blocked`, `target_built=blocked`, `default_smoke=blocked`
- Current failure: `source_authority_unverified`

## What Changed

The previous repair made the validated archive-loop source signal available for
terminal-success commands. This rerun used a stricter source acquisition shape,
but later build/toolchain work failed. Because the command was nonterminal, the
reducer still refused to satisfy `source_authority`.

Relevant successful source-acquisition shape:

- selected an authoritative release archive URL
- downloaded it with non-Python `curl`
- recorded `source_url`
- printed `sha256sum` for the archive
- validated archive contents with `tar -t`
- extracted the archive
- moved the extracted source root to `/tmp/CompCert`

The build then moved into external Flocq/toolchain repair and timed out/faulted
before producing `/tmp/CompCert/ccomp`.

## Decision

Do not run `proof_5` or broad measurement.

The next repair is still generic source-authority substrate work:

`nonterminal validated archive source proof must require ordered fetch -> hash -> validation -> extraction -> source-root move before later build failure`

