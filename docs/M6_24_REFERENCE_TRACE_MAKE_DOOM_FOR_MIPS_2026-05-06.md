# M6.24 Reference Trace: make-doom-for-mips

Date: 2026-05-06 JST

Purpose: capture Codex, Claude Code, and current-head mew behavior on
`make-doom-for-mips` so M6.24 implement_v2 repairs can compare step flow, not
only final reward.

## Runs

Reference commands:

```sh
uv run python scripts/run_harbor_reference_trace.py make-doom-for-mips codex --print-command
uv run python scripts/run_harbor_reference_trace.py make-doom-for-mips claude-code --print-command
```

mew command shape:

```sh
PYTHONPATH=.harbor harbor run -d terminal-bench/terminal-bench-2 \
  -i terminal-bench/make-doom-for-mips -k 1 -n 1 -y \
  --agent-timeout-multiplier 2 \
  --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent \
  --ak command_cwd=/app \
  --ak container_repo_root=/mew \
  --ak timeout_seconds=1800 \
  --ak command_template='mew work --oneshot ... --work-guidance selected_lane=implement_v2 ...'
```

## Results

All three live runs scored `0.0`, but they failed at different layers.

| agent | reward | Harbor errors | Harbor runtime | normalized total | first tool | first edit | commands | edits/tool writes | outcome |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Codex `gpt-5.5` | 0.0 | 1 `AgentTimeoutError` | 16m02s | 888.153s | 5.522s | 47.295s | 83 | 41 | reached valid-looking `frame.bmp`, then Harbor timed out before finalization |
| Claude Code `sonnet` | 0.0 | 1 `AgentTimeoutError` | 16m30s | 799.268s | 7.596s | none | 25 | 0 | spent the window planning/exploring custom libc/syscall strategy |
| mew `gpt-5.5` / `implement_v2` | 0.0 | 0 | 11m34s | local transcript only | turn 1 | n/a | 18 `run_command` + 6 polls | 36 tool calls | reached MIPS build/link path, then failed by sending shell verifier to `run_tests` |

Artifacts:

- Codex result:
  `proof-artifacts/terminal-bench/reference-trace/codex-make-doom-for-mips-20260506-152210/2026-05-06__15-22-11/result.json`
- Codex normalized trace:
  `proof-artifacts/terminal-bench/reference-trace/codex-make-doom-for-mips-20260506-152210/2026-05-06__15-22-11/make-doom-for-mips__n2YzfVT/normalized-trace/agent_trace.jsonl`
- Claude Code result:
  `proof-artifacts/terminal-bench/reference-trace/claude-code-make-doom-for-mips-20260506-152211/2026-05-06__15-22-11/result.json`
- Claude Code normalized trace:
  `proof-artifacts/terminal-bench/reference-trace/claude-code-make-doom-for-mips-20260506-152211/2026-05-06__15-22-11/make-doom-for-mips__ZdHHMDT/normalized-trace/agent_trace.jsonl`
- mew result:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-152558-reference-compare/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-152558-reference-compare/result.json`
- mew report:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-152558-reference-compare/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-152558-reference-compare/make-doom-for-mips__LJ7Jz95/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- mew implement_v2 transcript:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-152558-reference-compare/mew-m6-24-v2-rebaseline-make-doom-for-mips-speed1-20260506-152558-reference-compare/make-doom-for-mips__LJ7Jz95/agent/terminal-bench-harbor-smoke/unknown-task/implement_v2/transcript.json`

## Reference Step Shape

Codex step pattern:

1. Immediate cheap source and VM exploration:
   `find`, `ls`, `file`, targeted `sed` over `vm.js`, `doomgeneric_img.c`,
   and the Doom Makefile.
2. Toolchain/environment probe before heavy implementation:
   checks MIPS compilers, apt packages, object tools, source includes, platform
   dependencies, and VM syscall/ELF assumptions.
3. Source-preserving repair path:
   keeps Doom source and provided `doomgeneric_img.c`, adds support files and a
   dedicated MIPS build path instead of replacing the task with a stub.
4. Tight build/verify loop:
   repeatedly builds `doomgeneric_mips`, runs `node vm.js`, inspects runtime
   failure, and patches the VM/source compatibility surface.
5. Near-complete proof before timeout:
   trace records `/tmp/frame.bmp` at `1,024,054` bytes, matching a
   `640x400x32` BMP plus header. The Harbor agent timed out before final
   answer/report, so reward stayed `0.0`.

Claude Code step pattern:

1. Uses a read-only Explore subagent immediately.
2. Reads `vm.js`, `doomgeneric_img.c`, Makefile, and source headers before
   editing.
3. Identifies the same hard-runtime substrate: MIPS cross-compile plus syscall
   / libc / VM compatibility.
4. Installs `gcc-mipsel-linux-gnu` and continues broad C library dependency
   analysis.
5. Does not reach an edit before the Harbor agent timeout. Useful signal is
   mostly planning/exploration shape, not completion shape.

mew current-head step pattern:

1. Correctly uses `selected_lane=implement_v2` and
   `runtime_id=implement_v2_model_json_tool_loop`.
2. Starts with cheap directory/read/search probes and source-preserving MIPS
   build strategy.
3. Installs/checks MIPS toolchain, attempts Makefile/object selection repairs,
   and reaches link-level repairs with `_init` / `_fini` stubs.
4. Fails one verifier command because `file` is unavailable in the container.
5. Final blocker is tool-contract misuse: the model sends a multi-line shell
   verifier to `run_tests`, but `run_tests` is argv-only and returns:
   `run_tests executes one argv command without a shell; use run_command for
   shell orchestration`.

## Mew Gap

This run is better than the earlier false-finish runs:

- no false `finish`;
- source-preserving path is maintained;
- hard-runtime profile is active enough to avoid a handcrafted surrogate;
- terminal output projection no longer triggers the earlier provider
  `IncompleteRead` failure.

The remaining observed gap is narrower and more actionable:

```text
tool_contract_selection_gap:
  shell compound verifier -> should use run_command
  argv-only run_tests -> should reject or auto-route before spending final turn
```

Secondary efficiency gap:

```text
reference near-complete path:
  Codex reaches 640x400 frame evidence before timeout

mew path:
  reaches build/link repair but spends many turns rediscovering source roles and
  then loses the final verifier turn to tool misuse
```

## Next Repair

Do not add Doom-specific prompt text. The generic repair should be one of:

1. Tool selection guard:
   if a `run_tests` request contains shell metacharacters, newlines, `cd`,
   heredoc, `set -e`, pipes, redirects, or multiple commands, reject with a
   strong correction or route it to `run_command`.
2. Final verifier recovery turn:
   if the only final failure is `run_tests` argv-only misuse and wall budget
   remains, spend one bounded correction turn, preserving the verifier command.
3. Reference-step comparison:
   use this doc plus the normalized Codex trace to require hard-runtime tasks
   to maintain the source-preserving MIPS/VM repair path and avoid repeated
   source-role rediscovery after the build frontier is known.

Pre-speed gate for the next live proof:

1. focused unit test for `run_tests` shell misuse detection or routing;
2. exact replay/dogfood on the `20260506-152558-reference-compare` artifact;
3. emulator update if replay cannot expose the final tool-contract misuse;
4. one same-shape `make-doom-for-mips` `selected_lane=implement_v2` speed run.

## Controller Note

The Codex reference is not a clean Terminal-Bench pass in this run because the
Harbor agent timeout fired. Still, its trace is valuable: it shows the target
step shape and demonstrates that the task can reach valid frame evidence within
the same broad wall-clock window when the agent keeps a tight source-preserving
build/verify loop.
