# M6.24 Acceptance Evidence Structure: `compile-compcert` Speed Rerun

Date: 2026-05-01

## Result

- Job: `mew-m6-24-acceptance-evidence-structure-compile-compcert-1attempt-20260501-1750`
- Root result: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-acceptance-evidence-structure-compile-compcert-1attempt-20260501-1750/result.json`
- Trial result: `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-acceptance-evidence-structure-compile-compcert-1attempt-20260501-1750/compile-compcert__yTvXz74/result.json`
- Score: `0.0`
- Runner errors: `0`
- Runtime: about `30m 42s`

## Failure Shape

This was not an acceptance-evidence regression. The external verifier failed
because `/tmp/CompCert/ccomp` did not exist.

Observed chain:

1. mew fetched a VCS-generated CompCert `v3.13.1` source archive.
2. It installed distro Coq/Flocq prerequisites.
3. It probed configure help with a narrow filter:
   `grep -Ei 'coq|menhir|ignore|version'`.
4. That probe hid any `external` / `use-external` / `prebuilt` branch wording.
5. It tried `-ignore-coq-version`, then hit a dependency/API mismatch:
   `Z_div_mod_eq was not found in the current environment`.
6. Instead of broadening the source help probe and choosing a cheap
   source-provided external/prebuilt branch, it started a version-pinned OPAM
   Coq `8.16.1` source-toolchain build.
7. The toolchain build consumed the remaining wall budget and timed out before
   `ccomp` existed.

## Classification

Gap class: `long_dependency_toolchain_build_strategy_contract`

Selected generic repair:
`external_branch_help_probe_too_narrow_before_source_toolchain`

Layer: `profile_contract`

This complements the existing
`compatibility_branch_budget_contract_missing` blocker. That blocker catches
late commitment after an external/prebuilt branch is visible. This repair
catches the earlier case where the help probe itself was too narrow to surface
that branch before heavy source-toolchain construction begins.

## Next Action

Add a generic resume blocker and LongDependencyProfile guidance:

- If a long dependency/source-build task has missing final artifacts,
- and a configure/project help probe was filtered without
  `external` / `use-external` / `prebuilt` / `system` / `library` terms,
- and dependency/API mismatch appears,
- and the session then starts a version-pinned source-built toolchain,
- then tell the worker to inspect unfiltered or broader source help before
  continuing heavy alternate-toolchain work.

After repair and review, rerun one same-shape `compile-compcert` speed_1 before
another proof_5 or broad measurement.
