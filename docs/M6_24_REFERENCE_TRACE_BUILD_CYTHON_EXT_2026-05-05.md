# M6.24 Reference Trace: build-cython-ext

Date: 2026-05-05 JST

Purpose: capture Codex and Claude Code behavior on the active M6.24
`build-cython-ext` gap, then turn the measured reference pattern into a mew
improvement plan.

## Runs

Commands:

```sh
uv run python scripts/run_harbor_reference_trace.py build-cython-ext codex
uv run python scripts/run_harbor_reference_trace.py build-cython-ext claude-code
```

Both runs used Harbor built-in reference agents and post-task trace
normalization only.

## Results

| agent | reward | Harbor runtime | normalized total | first command | first edit | first verifier | commands | edits | verifier runs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Codex `gpt-5.5` | 1.0 | 6m25s | 326.275s | 2.817s | 16.631s | 26.773s | 30 | 36 | 4 |
| Claude Code `sonnet` | 1.0 | 6m01s | 309.230s | 3.388s | 128.681s | 291.216s | 21 | 18 | 1 |

Artifacts:

- Codex result:
  `proof-artifacts/terminal-bench/reference-trace/codex-build-cython-ext-20260505-121830/2026-05-05__12-18-31/result.json`
- Codex normalized trace:
  `proof-artifacts/terminal-bench/reference-trace/codex-build-cython-ext-20260505-121830/2026-05-05__12-18-31/build-cython-ext__L5ecLEA/normalized-trace/agent_trace.jsonl`
- Claude Code result:
  `proof-artifacts/terminal-bench/reference-trace/claude-code-build-cython-ext-20260505-121830/2026-05-05__12-18-31/result.json`
- Claude Code normalized trace:
  `proof-artifacts/terminal-bench/reference-trace/claude-code-build-cython-ext-20260505-121830/2026-05-05__12-18-31/build-cython-ext__C9zPPEB/normalized-trace/agent_trace.jsonl`

## Reference Behavior

Codex pattern:

- Clones the target repository immediately.
- Reads setup and environment quickly.
- Runs a broad symbol search early:
  `numpy`, `np.*`, `numpy.distutils`, `cython`, extension build markers.
- Builds/installs, runs a behavior smoke, and sees compatibility failures.
- Promotes the failure family into a broad sibling search:
  `fractions import gcd`, `np.*` / `n.*` removed aliases.
- Applies a mechanical repo-wide compatibility slice before another broad
  verify loop.
- Rebuilds, reinstalls, runs targeted tests, then broader repository tests.

Claude Code pattern:

- Spends longer before first edit, but performs the same conceptual move.
- Searches deprecated NumPy aliases across `*.py`, `*.pyx`, and `*.pxd`.
- Edits many sibling files before the final verifier.
- Runs one late broad verifier after the compatibility frontier has been mostly
  closed.

Shared signal:

The winning strategy is not "know pyknotid" or "know NumPy aliases." It is:

1. observe a verifier/runtime failure family;
2. search for sibling anchors across the source tree;
3. treat those anchors as an active repair frontier;
4. complete the frontier edit slice before broad rebuild/test/finish.

## Mew Gap

Current mew position from `ROADMAP_STATUS.md` and the latest active artifacts:

- Current-head `build-cython-ext` remains `0/1`.
- Latest selected class:
  `verified_sibling_repair_frontier_not_exhausted`.
- Current subtype:
  `repository_test_tail_frontier_not_exhausted_before_wall_timeout`.
- Latest current-head proof still reaches real build/install/runtime evidence,
  but external verifier remains red around NumPy 2.x compatibility and
  repository-test tail failures.

The reference traces confirm the existing selected class. The next repair should
not be another task-specific prompt patch. The missing substrate is an explicit
frontier object and action policy that force mew to finish a visible
same-family repair set before rediscovery, broad reinstall/test cycling, or
finish.

## Improvement Plan

### 1. Add an active compatibility frontier

Represent a compact frontier in resume/work state:

```text
family: verifier/runtime symbol-compatibility failure
evidence: failing command id, stack frames, missing symbols, source paths
anchors: grep/rg queries and matched files
required_action: apply a complete sibling edit slice before broad verify
proof: targeted behavior smoke + repository-test tail
```

This must be generic. It should be populated from verifier output, stack traces,
and search results, not from fixed `build-cython-ext` recipes.

### 2. Change action selection when a frontier exists

When an active frontier has exact sibling anchors:

- prefer one complete multi-file/same-family edit slice;
- allow a mechanical edit command only when anchors are exact and followed by
  diff/proof;
- block another broad install/test loop if the known frontier has not been
  edited or explicitly rejected;
- preserve the frontier across compact recovery and wall-time handoff.

### 3. Strengthen finish evidence for runtime components

Load/path evidence is not enough. A finish should require:

- compiled extension import/load proof;
- at least one exported behavior invocation or task-specific repository test
  tail;
- no known failing repository-test tail frontier.

This matches the current M6.24 direction and is consistent with the reference
behavior.

### 4. Add comparable mew timeline extraction

The new reference trace normalizer gives `first_edit_seconds`,
`first_verifier_seconds`, and command counts for Codex/Claude. For mew,
normalization should also support the current mew report shape so the same
fields can be compared directly:

- first model-visible edit proposal;
- first command / first verifier;
- count of broad rebuild/test cycles before closing a known frontier;
- time spent after first known sibling anchors before first edit.

### 5. Pre-speed gate

Before spending another live `build-cython-ext` proof:

1. focused UT for frontier extraction and resume projection;
2. replay on latest `build-cython-ext` artifact;
3. dogfood scenario on the same artifact;
4. same-shape emulator for repository-test-tail frontier;
5. exactly one live `build-cython-ext speed_1` with
   `selected_lane=implement_v2`.

Stop condition: the v2 speed run is useful only while it follows the reference
step shape. If it leaves the shared Codex/Claude Code pattern before reaching
the known final-verifier gap shape, stop live speed spending, preserve the
artifact, and debug with replay/dogfood/trace comparison before another run.

## Next Controller Chain

```text
M6.24 -> build-cython-ext reference traces pass -> selected gap confirmed ->
active compatibility frontier v0 -> action selection frontier lock ->
finish evidence guard -> mew timeline normalization -> UT/replay/dogfood/emulator ->
one speed_1
```
