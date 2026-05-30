# M6.23.2 Phase 4 Managed Exec Proof - 2026-05-05

Status: passed

Commit: `0cecdb5` (`Add implement v2 managed exec spike`)

## Scope

Phase 4 added a default-off `implement_v2` exec-mode spike. It is not wired into
the production work loop and does not grant completion credit.

Delivered:

- provider-native fake exec path for `run_command`, `run_tests`,
  `poll_command`, `cancel_command`, and `read_command_output`;
- paired `ToolResultEnvelope` results for terminal, nonterminal, failed,
  cancelled, and rejected command lifecycle states;
- managed command output refs and terminal evidence refs in proof manifests;
- explicit `lane_config.mode == "exec"` gate before side effects;
- provider call identity prevalidation before side effects;
- resident mew-loop rejection for direct and shell-segment commands;
- `run_tests` single-argv verifier boundary for shell operators, backgrounding,
  redirection, and explicit shell wrappers;
- cleanup projection for unpolled yielded commands as paired `interrupted`
  results.

## Verification

Local checks:

```text
uv run pytest --no-testmon tests/test_implement_lane.py tests/test_work_lanes.py -q
=> 57 passed, 2 subtests passed

uv run ruff check src/mew/implement_lane tests/test_implement_lane.py tests/test_work_lanes.py
=> All checks passed

git diff --check
=> pass
```

Review:

- `codex-ultra` session `019df87c-7dd0-70f2-be76-4098ae875cd6`
- Final verdict: PASS
- Reviewed focus: call identity prevalidation, shell/resident-loop rejection,
  yielded command cleanup projection, explicit exec-mode gate, and lifecycle
  proof pairing.

## Phase 5 Entry

Next phase:

```text
M6.23.2 Phase 5: write/edit/apply_patch behind approval
```

Phase 5 must keep `implement_v2` default-off, maintain paired provider-visible
results, and preserve the Phase 4 rule that no fake helper side effects occur
before identity and mode gates pass.
