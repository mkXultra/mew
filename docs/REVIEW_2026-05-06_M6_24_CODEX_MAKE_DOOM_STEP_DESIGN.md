# Review: Codex make-doom-for-mips Step Design for M6.24

Date: 2026-05-06 JST

Scope: local mew, local Codex source at `references/fresh-cli/codex`, no
internet lookup, no mew source changes.

## Executive Conclusion

Codex did not pass `terminal-bench/make-doom-for-mips`; Harbor timed out and
reward stayed `0.0`. The useful signal is step shape: Codex reached a
valid-looking `640x400x32` frame artifact while maintaining a source-preserving
build/runtime repair loop.

mew current-head reached the same broad frontier, including MIPS build/link
work, but lost the final verifier by sending a shell-shaped command to argv-only
`run_tests`.

Immediate import target:
- runtime/tool-dispatch recovery for shell-shaped `run_tests` calls;
- compact hard-runtime source/frontier state that prevents rediscovery;
- no Doom-specific prompt patches.

## Importable Codex STEPs

Trace source: `docs/M6_24_REFERENCE_TRACE_MAKE_DOOM_FOR_MIPS_2026-05-06.md:58`,
`:91`, `:105`.

Import these generic STEPs:

1. **Cheap source/runtime preflight.**
   Identify entrypoints, harness/runtime source, build files, final artifact
   path, and available toolchain before expensive edits.

2. **Toolchain/environment probe before heavy implementation.**
   Prove the compiler/runtime/object-tool substrate before large edits or long
   builds. The generic behavior is substrate validation, not any MIPS package.

3. **Source-preserving repair path.**
   Keep provided source and harness central. Track source inventory, prohibited
   surrogates, current build target, and final artifact path as loop state.

4. **Tight build/run/failure-inspect/patch loop.**
   Once a build frontier exists, make the latest runtime/build failure drive the
   next smallest repair instead of broad rediscovery.

5. **Exact final artifact proof.**
   Tie final proof to the verifier-visible artifact path and run a
   verifier-shaped command after the last compatibility change.

6. **Wrong-tool recovery.**
   Recover high-confidence tool misroutes at the runtime boundary when the
   intended action is clear and safe.

## Codex Source Patterns

### Tool-result-centered loop

Codex's turn loop is built around sampling, executing tool calls, and feeding
tool output back into the next sampling request.

Sources: `references/fresh-cli/codex/codex-rs/core/src/session/turn.rs:118`,
`:375`, `:445`.

When the model emits a tool call, Codex records it, queues execution, and marks
the request as needing follow-up.

Sources:
`references/fresh-cli/codex/codex-rs/core/src/stream_events_utils.rs:199`,
`:228`, `:253`.

Nonfatal tool-call errors can be returned to the model as tool output and also
force follow-up.

Sources:
`references/fresh-cli/codex/codex-rs/core/src/stream_events_utils.rs:317`,
`:337`.

M6.24 implication:
- a tool-contract error should not necessarily consume the final meaningful
  action if the rejected command can be corrected or re-routed deterministically.

### Clear shell-command surface

Codex's modern `exec_command` exposes `cmd: string` as the shell command.

Sources: `references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs:19`,
`references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs:45`.

That string is translated internally into shell argv (`zsh`/`bash`/`sh` use
`-lc` or `-c`; PowerShell/Cmd use native command modes).

Sources:
`references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs:428`,
`references/fresh-cli/codex/codex-rs/core/src/shell.rs:41`.

Codex also has an older argv-style `shell` tool, but its prompt says most
commands should be prefixed with `["bash", "-lc"]`; `shell_command` exposes a
script string directly.

Sources: `references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs:136`,
`:199`.

M6.24 implication:
- Codex avoids much of mew's `run_command` vs `run_tests` ambiguity because its
  main command surface naturally accepts shell orchestration.
- mew intentionally splits shell-capable `run_command` from argv-only
  `run_tests`, so mew needs a deterministic bridge for shell-shaped verifier
  commands.

### Wrong-tool recovery exists for some surfaces

Codex intercepts `apply_patch` invoked through shell/exec, warns the model to use
the patch tool, and applies the verified patch anyway.

Sources:
`references/fresh-cli/codex/codex-rs/core/src/tools/handlers/apply_patch.rs:468`,
`:487`, `:491`.

M6.24 implication:
- do not copy Codex patch grammar now;
- do copy the generic pattern: high-confidence misroutes can be recovered at the
  runtime boundary when semantics are clear.

### Cheap exploration is mostly emergent

Codex's base prompt says to keep going, use `apply_patch`, fix root causes,
validate work, and prefer `rg`/`rg --files`.

Sources:
`references/fresh-cli/codex/codex-rs/protocol/src/prompts/base_instructions/default.md:123`,
`:149`, `:260`.

I did not find a default execute-mode Codex module that explicitly enforces
"cheap exploration before expensive action" for coding tasks. In this trace, the
behavior appears mostly emergent from model behavior, prompt nudges, and tool
affordances.

## Mew Comparison

### Tool-contract selection gap

mew v2 already normalizes `command`, `cmd`, and `argv`, reducing schema spelling
failures.

Sources: `src/mew/implement_lane/exec_runtime.py:80`, `:208`.

For `run_command`, mew detects unquoted shell surface and executes through a
shell when needed. For `run_tests`, it rejects shell surface and explicit shell
interpreter use.

Sources: `src/mew/implement_lane/exec_runtime.py:232`, `:269`, `:278`,
`:312`.

The prompt also states the intended contract.

Sources: `src/mew/work_loop.py:6504`, `:6537`.

Gap:
- rejection is correct but insufficient near the end of a timed hard-runtime
  run. The rejected command should be auto-routed or force a bounded correction
  turn with the command preserved.

### Terminal-failure reaction exists

implement_v2 can extend one turn after terminal command failure.

Sources: `src/mew/implement_lane/v2_runtime.py:153`, `:1187`.

Gap:
- `run_tests` shell-contract failure should be a specific recoverable
  tool-selection failure, not just another failed verifier.

### Source-preserving guidance exists, but is prompt-heavy

mew already instructs hard-runtime work to preserve compatibility frontier,
execution contracts, source inventory, prohibited surrogates, and exact `/tmp`
artifact transfer.

Sources: `src/mew/work_loop.py:6496`, `:6514`, `:6526`, `:6527`, `:6528`.

Gap:
- the durable state should explicitly carry current source roles, build
  frontier, latest runtime failure, final artifact path, and next cheapest
  verifier-shaped command.

## Recommendations

### Import now before next speed proof

1. Add deterministic `run_tests` shell-surface recovery.
   If a v2 `run_tests` call contains unquoted shell operators, newlines,
   heredocs, redirection, or explicit shell interpreter use, and `allow_shell` is
   true, route it to `run_command` before execution. Preserve cwd, timeout,
   foreground budget, execution_contract, and proof role.

2. If auto-route is too permissive, force one correction turn.
   The failed result should quote the rejected command and instruct the model to
   retry the same command with `run_command`. Ensure this exact failure qualifies
   for terminal-failure reaction at the base turn limit.

3. Add focused tests before another speed run.
   Cover multi-line `run_tests`, `set -e`/pipe/redirect `run_tests`, simple argv
   `run_tests`, and shell-shaped verifier routing to `run_command`.

4. Replay the exact failed artifact before live proof.
   Use the `20260506-152558-reference-compare` transcript/report to prove the
   emulator exposes the final tool-contract misuse and the fix repairs it.

5. Persist hard-runtime source-role state after initial probe.
   Keep objective, source inventory, harness/runtime source, build target, final
   artifact path, prohibited surrogates, latest build frontier, latest runtime
   failure, and next verifier-shaped command.

### Design now, implement later

1. Unify the v2 verifier/shell contract.
   Consider clearer schemas such as `run_argv`, `run_shell`, and
   `verify_command(shell=true|false)`, or one command tool plus proof metadata.

2. Make source-role/frontier state deterministic.
   Integrate source inventory and current build/runtime frontier with
   `compatibility_frontier` so broad rediscovery and setup restarts can be
   redirected by state.

3. Generalize wrong-tool recovery.
   Design a small table of safe recoveries instead of copying Codex's patch
   interception wholesale.

4. Improve long-command continuation ergonomics.
   mew already has managed commands, `poll_command`, and `read_command_output`;
   deeper Codex-like streaming/yield behavior can wait unless long builds remain
   the bottleneck.

### Do not import / not relevant

1. Doom-specific syscall, VM, Makefile, or frame-size instructions.
2. Full Codex CLI architecture or tool registry as a mew v2 replacement.
3. Codex Harbor timeout behavior.
4. Claude Code Explore-subagent strategy for this immediate repair.
5. More broad prompt churn without a runtime guard.

## Bottom Line

For the next M6.24 speed proof, fix the deterministic boundary first:
shell-shaped final verifiers must not die inside argv-only `run_tests`.

After that, improve hard-runtime continuity by making source roles and the
active build/runtime frontier compact state. Codex's advantage in this trace is
mostly step shape plus tool affordance, not a hidden Doom-specific algorithm.
