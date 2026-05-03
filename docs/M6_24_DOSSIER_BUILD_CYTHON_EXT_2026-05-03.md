# M6.24 Dossier: build-cython-ext

Date: 2026-05-03

Purpose: prevent the next `build-cython-ext` repair from becoming another
task-specific prompt patch. This dossier summarizes the prior repair loop and
selects the next generic gap class for the M6.24 controller.

## Current Position

Frozen Codex target: `5/5`.

Mew:

- best observed: `1/5`
- latest current-head recheck: `0/1`
- latest Harbor errors: `0`

Primary artifacts:

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-build-cython-ext-5attempts-20260428-0054/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-build-cython-ext-5attempts-run-tests-recover-20260428-0300/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-build-cython-ext-5attempts-verifier-agenda-20260428-0710/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-build-cython-ext-5attempts-wall-timeout-reduced-20260428-0755/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-build-cython-ext-5attempts-sibling-search-20260428-0818/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-build-cython-ext-5attempts-same-file-batch-wait-20260428-0841/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-rebaseline-build-cython-ext-1attempt-20260503-1936/result.json`

## Chronology

| Attempt | Score | Movement | Main failure after attempt |
|---|---:|---|---|
| Initial batch | 0/5 | Established baseline | Missing read path inside read-only batch became terminal `tool_failed`; one progressed trial repeated install after source edits. |
| Missing-read batch repair | 0/5 | Missing-read terminal stop mostly removed | `run_tests` was not granted in the generic Harbor command path. |
| `--allow-verify` harness repair | 0/5 | Verifier tool became available | Repeat guard blocked legitimate rebuild/install after workspace edits. |
| Repeat reset after writes | 0/5 | Repeat blocker reduced | Stale exact-text edits and remaining compatibility loop blockers. |
| Stale edit recovery / git-status repairs | 0/5 | Tool-loop robustness improved | `run_tests` and generated-artifact missing paths still stopped near-solution attempts. |
| Direct `run_tests` recovery | 1/5 | First passing trial | Remaining attempts lost context around git inspection, pytest deps, generated metadata, or timed out near solution. |
| Verifier agenda and missing-dir observations | 0/5 | Hidden verifier failures became visible in resume | Same-family `fractions.gcd`, `np.float`, `np.complex` repair set was not completed before wall/model timeout. |
| Reduced wall-timeout model turns | 0/5 | Attempts reached deeper verifier state | Remaining blockers concentrated on same-family compatibility symbols and repository-test tail. |
| Verifier sibling searches | 1/5 | One trial reached full success; failed attempts found concrete sibling anchors | Duplicate same-file write batch normalized to `wait`; short budget near solution remained. |
| Same-file batch blocker repair | 0/5 | Duplicate same-file batch wait did not recur | All trials wall-timed near solution; verifier tails still concentrated on source compatibility siblings and repository tests. |
| Current-head architecture recheck | 0/1 | Execution-contract and prompt-section architecture moved the failure deeper: extension build/import, neutral README smoke, and 10/11 external verifier tests passed. | `work_report.stop_reason=wall_timeout`; remaining failure is repository-test tail, specifically upstream `tests/test_spacecurve.py::test_reconstructed_space_curve`, after mew found but did not finish the next narrow source repair before wall budget expired. |

## Repaired Or Rejected Duplicate Fixes

Already repaired or ruled out:

- read-only batch missing path should not terminate the whole work loop
- `run_tests` must be available in generic implementation-lane Harbor runs
- repeating install/build/test after source writes is valid evidence seeking
- stale exact-text edits need repair anchors rather than terminal stop
- direct verifier failures can become repair agenda instead of terminal stop
- missing generated artifact paths should be observations, not fatal reads
- duplicate same-file write batches should continue as `edit_file_hunks` or a
  narrower complete slice

Do not repeat these as the next selected repair unless a current artifact proves
they regressed.

Explicitly rejected:

- adding a `build-cython-ext`, `pyknotid`, NumPy, or Cython-specific solver
- teaching a fixed list of compatibility symbols as benchmark-specific rules
- spending another live proof before UT/replay/dogfood/emulator can detect the
  selected same-shape failure

## Selected Gap Class

Selected class:
`verified_sibling_repair_frontier_not_exhausted`.

Current-head subtype:
`repository_test_tail_frontier_not_exhausted_before_wall_timeout`.

Definition:

The loop can extract verifier failure families and search anchors, but it does
not reliably turn that evidence into an explicit repair frontier that must be
exhausted before another broad reinstall/verify/finish cycle or wall-time
handoff.

Signals from artifacts:

- Passing trial `build-cython-ext__E7W6FEZ` proves the generic path can solve the
  task when it completes the compatibility repair set.
- Failing trial `build-cython-ext__3XSsa4R` had concrete search anchors for
  `from fractions import gcd`, `n.float`, and `np.float`, and its next step was
  to patch all relevant aliases, reinstall, and rerun smoke/tests.
- Latest failed trials after the same-file repair no longer stopped on the
  duplicate write-batch blocker, but still wall-timed around the same
  compatibility family and repository-test tail.
- Current-head trial `build-cython-ext__MQPEBk8` passed the main install/import
  and README example path, and external verifier output shows `10 passed, 1
  failed`. The remaining failure is no longer broad source acquisition or Cython
  build setup; it is a repository-test-tail repair frontier that did not get a
  final edit/proof before wall timeout.

Why this is generic:

- Many implementation tasks fail by one verifier family appearing in several
  source or generated locations.
- The correct behavior is not "know NumPy aliases"; it is "when verifier output
  names a same-family failure and search anchors exist, preserve that as a
  concrete frontier and complete the visible sibling repair set before moving
  to a broad cycle."

## Next Repair Shape

Preferred layer: detector/resume state plus implementation-lane policy.

Candidate behavior:

- promote `verifier_failure_repair_agenda.sibling_search_queries` and
  `search_anchor_observations` into a compact active sibling repair frontier
  when the same family appears in multiple source locations;
- make the frontier visible in resume text with the files, anchors, family, and
  required next action;
- during ACT/THINK selection, prefer one complete same-file or multi-file
  sibling edit slice before another install/test loop when exact anchors are
  already available;
- treat a timeout or wait before applying known sibling repairs as a recoverable
  frontier-continuation state, not as permission to rediscover the project.
- preserve the external verifier repository-test tail as first-class failure
  evidence. A run that has passed the main smoke path and has one remaining
  repository test should not spend repeated turns rediscovering packaging or
  Cython build facts.

Rollback condition:

- If the change starts creating task-specific compatibility recipes or large
  prompt-only guidance, stop and redesign around a small frontier object.
- If replay/dogfood cannot express the failure, add instrumentation/emulator
  first rather than spending Harbor budget.

## Pre-Speed Operation

Before any live `build-cython-ext` `speed_1`, run against the current-head
artifact first:

1. focused UT for verifier agenda / sibling frontier / same-file edit behavior;
2. `mew replay terminal-bench` against the latest relevant saved
   `build-cython-ext` artifact with assertions matching the selected frontier
   failure;
3. `mew dogfood --scenario m6_24-terminal-bench-replay` against the same saved
   artifact and assertion shape;
4. a same-shape emulator. If no generic build/FFI/runtime compatibility
   emulator exists, build the smallest fixture that replays a raw model action
   and resume state containing same-family verifier failures plus sibling
   search anchors.

The first saved artifact for this pre-speed operation is:
`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-rebaseline-build-cython-ext-1attempt-20260503-1936`.

Current pre-speed status:

- `mew replay terminal-bench` passes on the current-head artifact with
  `--task build-cython-ext --assert-mew-exit-code 1 --assert-external-reward 0`.
- `mew dogfood --scenario m6_24-terminal-bench-replay` now passes on the same
  artifact after removing the scenario's hard-coded `compile-compcert` task
  filter and adding `--terminal-bench-task`.
- `mew dogfood --scenario m6_24-repository-test-tail-emulator` passes on the
  same artifact. It detects that main smoke/example usage passed, the external
  verifier failed on the repository-test wrapper, and mew stopped by
  `wall_timeout` before closing that frontier.

Only after all four pass, spend exactly one `build-cython-ext` `speed_1`.

## Controller Chain

```text
M6.24 -> verified_sibling_repair_frontier_not_exhausted -> current-head repository-test-tail artifact -> replay/dogfood/emulator classification -> implementation_profile/tiny lane -> create frontier repair + pre-speed emulator -> same-shape build-cython-ext speed_1 only after pre-speed passes
```
