# Command Classification Reference Review - 2026-05-03

## Scope

Both reference directories were present:

- `references/fresh-cli/codex`
- `references/fresh-cli/claude-code`

Question reviewed: whether Codex CLI or Claude Code distinguish pure source fetch/readback from long build/install/smoke shell commands in a way comparable to mew's M6.24 long-command budget repair.

## Direct Answer

Codex CLI and Claude Code do have shell-command classification logic, but not a mew-like long-build/fetch budget classifier.

Their pattern is different:

- classify shell for safety, read-only permission decisions, prompt/approval routing, UI summaries, and exit-code interpretation;
- handle long-running commands through process lifecycle architecture: timeout, streaming output, background/yielded process handles, polling, and sandbox retry;
- avoid some shell ambiguity by using dedicated tools for edits/read/search where possible.

Mew's current M6.24 classifier is more domain-specific: it attaches managed long-command budget to planned build/dependency/smoke stages, and explicitly prevents pure source acquisition/readback from being promoted merely because a URL/path contains words like `make`.

## Codex CLI Findings

### Shell Classification

Codex has explicit shell classification, but it is safety/read-only oriented:

- `references/fresh-cli/codex/codex-rs/shell-command/src/command_safety/is_safe_command.rs:10` defines `is_known_safe_command`.
- `is_known_safe_command` normalizes `zsh` to `bash`, checks Windows safety, direct safe commands, and plain `bash -lc`/`zsh -lc` scripts where every parsed segment is safe (`is_safe_command.rs:10-45`).
- The direct safe allowlist includes read/list/search-ish commands such as `cat`, `grep`, `head`, `ls`, `pwd`, `tail`, `wc`, with special handling for `base64`, `find`, `rg`, `git status/log/diff/show/branch`, and `sed -n` (`is_safe_command.rs:47-182`).
- `curl`, `wget`, `make`, `opam`, and build/install semantics are not classified here as long build/fetch. A pure `curl -L ...make-4.4.tar.gz` is not treated as "build"; it is just not known-safe by this allowlist.
- `references/fresh-cli/codex/codex-rs/shell-command/src/command_safety/is_dangerous_command.rs:7-29` checks direct and plain shell-lc commands for dangerous operations; the Unix direct check mainly flags `rm -f/-rf` and recurses through `sudo` (`is_dangerous_command.rs:156-168`).
- Git global option parsing is safety-specific: `find_git_subcommand` and `git_global_option_requires_prompt` prevent global-option bypasses (`is_dangerous_command.rs:56-80`, `108-154`).

Codex parses shell-lc scripts conservatively:

- `references/fresh-cli/codex/codex-rs/shell-command/src/bash.rs:11-20` uses `tree-sitter-bash`.
- `try_parse_word_only_commands_sequence` accepts only plain commands joined by `&&`, `||`, `;`, or `|`, and rejects redirections, substitutions, control flow, etc. (`bash.rs:22-95`).
- `parse_shell_lc_plain_commands` and `parse_shell_lc_single_command_prefix` expose this to safety/policy code (`bash.rs:112-137`).

Codex also has command-summary metadata, not a build classifier:

- `references/fresh-cli/codex/codex-rs/shell-command/src/parse_command.rs:25-48` parses lossy human-readable metadata.
- `parse_command_impl` splits connectors, tracks `cd`, and summarizes read/list/search/unknown commands (`parse_command.rs:1275-1335`).
- `parse_shell_lc_commands` summarizes plain bash-lc scripts and drops small formatting helpers (`parse_command.rs:1818-1947`).
- The protocol enum is only `Read`, `ListFiles`, `Search`, and `Unknown` (`references/fresh-cli/codex/codex-rs/protocol/src/parse_command.rs:7-31`).

### Exec Lifecycle, Long-Running Handling, and Output

Classic shell calls are short-timeout execs:

- `ShellHandler::to_exec_params` creates `ExecParams` with timeout, cwd, sandbox permissions, and `ExecCapturePolicy::ShellTool` (`references/fresh-cli/codex/codex-rs/core/src/tools/handlers/shell.rs:92-114`).
- `ShellCommandHandler::to_exec_params` wraps a string command through the user's shell and produces the same exec parameters (`shell.rs:142-169`).
- `ShellHandler::is_mutating` and `ShellCommandHandler::is_mutating` use `!is_known_safe_command(...)` (`shell.rs:196-205`, `301-320`).
- `ShellHandler::run_exec_like` centralizes env setup, escalation guard, `apply_patch` interception, approval policy creation, `ShellRequest` construction, orchestration, and output formatting (`shell.rs:398-596`).
- Classic exec default timeout is 10 seconds (`references/fresh-cli/codex/codex-rs/core/src/exec.rs:51`).
- `consume_output` races child exit against timeout/cancel, kills the process group on timeout, and drains output with a guard (`exec.rs:1230-1329`).
- Output is capped for retained bytes and live deltas (`exec.rs:64-72`, `1331-1385`), then truncated for model consumption (`references/fresh-cli/codex/codex-rs/core/src/tools/mod.rs:98-119`).

Codex's long-running answer is Unified Exec, not command-type classification:

- Unified Exec is described as interactive process execution with approvals/sandboxing, process handles, streaming output, and metadata (`references/fresh-cli/codex/codex-rs/core/src/unified_exec/mod.rs:1-23`).
- It has yield/output/process caps: yield time up to 30s, default max background terminal timeout 300s, default output tokens 10k, output bytes 1 MiB, and max 64 processes (`unified_exec/mod.rs:59-67`).
- `UnifiedExecProcessManager::exec_command` opens a sandboxed session, starts streaming, stores live processes before the initial yield, collects output until the yield deadline, and returns `process_id` when still alive (`references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs:231-405`).

### Approval, Sandbox, and Patch Flow

- `create_exec_approval_requirement_for_command` parses commands for exec policy, applies policy rules, and returns forbidden/needs-approval/skip (`references/fresh-cli/codex/codex-rs/core/src/exec_policy.rs:235-330`).
- Unmatched commands allow known-safe commands directly, prompt/forbid dangerous commands depending policy, and otherwise rely on sandbox/approval policy (`exec_policy.rs:583-679`).
- `commands_for_exec_policy` uses plain shell-lc parsing or heredoc-prefix parsing for policy matching (`exec_policy.rs:701-713`).
- `ToolOrchestrator` is the central approval -> sandbox -> attempt -> retry path (`references/fresh-cli/codex/codex-rs/core/src/tools/orchestrator.rs:1-8`, `105-205`, `224-357`).
- File edits are kept out of generic shell where possible: Codex exposes a dedicated `apply_patch` tool (`references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs:87-122`) and intercepts shell-invoked `apply_patch`, warning the model to use the tool instead (`references/fresh-cli/codex/codex-rs/core/src/tools/handlers/apply_patch.rs:469-567`).

## Claude Code Findings

### Bash Metadata and Classification

Claude Code has several classifications, but they serve UI, permission, and result interpretation:

- `BashTool.tsx` defines progress and assistant blocking budgets: progress after 2s, assistant auto-background after 15s (`references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:54-57`).
- `isSearchOrReadBashCommand` classifies commands as search/read/list for collapsible UI; all non-neutral segments must be search/read/list (`BashTool.tsx:59-172`).
- `isSilentBashCommand` recognizes commands expected to produce no stdout (`BashTool.tsx:174-217`).
- The Bash schema exposes `command`, optional `timeout`, `description`, `run_in_background`, and `dangerouslyDisableSandbox` (`BashTool.tsx:219-259`).
- `COMMON_BACKGROUND_COMMANDS` includes `make`, `curl`, `wget`, `build`, `test`, etc., but only for logging command type when backgrounding, not for build/fetch budget classification (`BashTool.tsx:265-278`).
- `commandSemantics.ts` interprets exit codes for commands like `grep`, `rg`, `find`, `diff`, and `test`; it explicitly warns its heuristic base-command extraction is not security-grade (`references/fresh-cli/claude-code/src/tools/BashTool/commandSemantics.ts:1-6`, `31-89`, `108-140`).

Claude Code has a Bash classifier API in the tree, but this external reference build stubs it off:

- `references/fresh-cli/claude-code/src/utils/permissions/bashClassifier.ts:1-2` says classifier permissions are ANT-only.
- `isClassifierPermissionsEnabled()` returns `false` (`bashClassifier.ts:24-26`).
- `classifyBashCommand` always returns no match with reason "This feature is disabled" (`bashClassifier.ts:40-53`).

### Permissions, Read-Only Checks, and Sandbox Policy

- `bashToolHasPermission` does AST-based security parsing when available, asks on too-complex structures, and checks semantic concerns such as dangerous command names (`references/fresh-cli/claude-code/src/tools/BashTool/bashPermissions.ts:1663-1806`).
- It has sandbox auto-allow for sandboxed commands while still respecting explicit deny/ask rules (`bashPermissions.ts:1829-1843`).
- If classifier permissions are enabled, deny/ask prompt classifiers can run in parallel, but in this build they are disabled by the stub above (`bashPermissions.ts:1856-1971`).
- It validates command operators, redirections, paths, subcommands, and possible injection before allowing or asking (`bashPermissions.ts:1973-2075`, `2144-2371`).
- `checkReadOnlyConstraints` validates whether a bash command is read-only, including compound commands and sandbox/security checks (`references/fresh-cli/claude-code/src/tools/BashTool/readOnlyValidation.ts:1867-1990`).
- Tool execution starts speculative Bash classifier checks early if the feature is available (`references/fresh-cli/claude-code/src/services/tools/toolExecution.ts:734-752`), again for permission auto-approval, not build/fetch semantics.
- The prompt instructs the model to prefer dedicated tools for file search/read/edit/write over Bash and describes timeout/background behavior (`references/fresh-cli/claude-code/src/tools/BashTool/prompt.ts:275-368`).
- The sandbox prompt section tells the model to default to sandbox and use `dangerouslyDisableSandbox` only on explicit user request or evidence of sandbox-caused failure (`prompt.ts:172-260`).
- Tool UI buckets separate read-only tools, edit tools, and execution tools; Bash is in `Execution tools` (`references/fresh-cli/claude-code/src/components/agents/ToolSelector.tsx:49-62`).

### Long-Running, Timeout, Background, and Output Handling

Claude Code handles long commands by task lifecycle:

- `runShellCommand` starts shell execution with timeout, progress callback, sandbox choice, and auto-background eligibility (`BashTool.tsx:826-898`).
- On timeout, auto-background can move allowed commands into a background task instead of killing them (`BashTool.tsx:965-970`).
- In assistant mode, a blocking foreground Bash command can auto-background after 15s so the main agent remains responsive (`BashTool.tsx:973-982`).
- Explicit `run_in_background` returns a background task id immediately (`BashTool.tsx:985-1000`).
- Foreground progress waits 2s, then polls task output and can register a foreground task for manual backgrounding (`BashTool.tsx:1003-1143`).
- `Shell.exec` spawns a fresh shell process, wraps sandbox when enabled, and routes Bash stdout/stderr to a task output file in file mode (`references/fresh-cli/claude-code/src/utils/Shell.ts:181-286`, `316-345`).
- `ShellCommandImpl` either kills on timeout or calls the background callback when auto-background is enabled (`references/fresh-cli/claude-code/src/utils/ShellCommand.ts:135-140`, `263-365`).
- Background tasks keep output and notify on completion/failure; a stall watchdog stays silent on merely slow commands such as long builds and only notifies if the tail looks like an interactive prompt (`references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:28-31`, `44-104`, `180-252`, `293-473`).
- Output is file-backed/polled, has progress tailing, and is persisted/truncated for large outputs (`references/fresh-cli/claude-code/src/utils/task/TaskOutput.ts:21-31`, `77-164`, `297-312`; `references/fresh-cli/claude-code/src/utils/task/diskOutput.ts:23-31`; `BashTool.tsx:728-753`).

## Mew Comparison

Mew's M6.24 repair is a targeted long-build-budget classifier:

- `planned_long_build_command_budget_stage` calls recorded stage logic, then applies budget-specific promotion and pure-fetch guard (`src/mew/long_build_substrate.py:898-942`).
- Pure source acquisition is prevented from being promoted when the command uses source acquisition tools and has no non-fetch build segment (`src/mew/long_build_substrate.py:905-910`).
- Non-fetch build segments are recognized by parsed invoked command token, not by URL/path substrings: `make`, `ninja`, `cargo build`, `go build`, `npm run build`, `python -m build`, `opam install`, and `pip install` (`src/mew/long_build_substrate.py:945-979`).
- Source acquisition segment detection includes `curl`, `wget`, `tar`, `unzip`, `gh`, and relevant `git` subcommands, with extra remote-fetch/no-download-mode handling elsewhere (`src/mew/long_build_substrate.py:3083-3109`, `3718-3775`).
- `work_tool_long_command_budget_policy` uses `planned_long_build_command_budget_stage` and attaches `long_command_budget` only when the stage/policy applies (`src/mew/commands.py:6264-6360`, `6430-6479`, `7659-7672`).
- The repair doc states the intended guard directly: pure `curl -L` source fetch/readback remains non-managed-budget even if the URL/path contains build words like `make` (`docs/M6_24_COMPOUND_LONG_COMMAND_BUDGET_REPAIR_2026-05-03.md:52-67`).
- Focused tests cover compound configure/build/smoke promotion and pure source fetch/readback non-promotion (`tests/test_long_build_substrate.py:100-174`).

## Recommendation for Mew

Keep the current classifier, but keep it narrow.

It is solving a mew-specific product problem that the references mostly avoid through runtime architecture: when a planned command should enter mew's managed long-command budget. Codex/Claude do not offer a directly reusable build/fetch classifier.

The current pure fetch/readback guard aligns with the reference pattern in one important way: classify by executable command semantics and parsed command segments, not by incidental substrings in URLs, archive names, or paths. A URL containing `make` should not be enough to classify the shell call as a build.

Recommended constraints:

- Keep `planned_long_build_command_budget_stage` as budget-specific logic, not a generic shell classifier.
- Continue using invoked command tokens and segment boundaries for promotion.
- Treat source acquisition/readback as separate from build/install/smoke unless a non-fetch segment invokes a known build/install/smoke command.
- Prefer explicit lifecycle controls for truly long commands, following Codex/Claude architecture: yield/poll/background/process id/output persistence should carry most generic long-command handling.
- Add ecosystem coverage only when it corresponds to generic build semantics, not a single benchmark trace.

## Risks

- Overfitting to `compile-compcert`: `opam install`, `configure`, `make`, and final smoke are real generic patterns, but a classifier tuned around one failure can miss or over-promote other ecosystems.
- False positives from path/URL text: archive names like `make-4.4.tar.gz`, `build.tar.gz`, or `/tmp/build-output` must not imply build execution.
- False negatives for other real long builds: `nix build`, `bazel build`, `cmake --build`, `meson compile`, `gradle build`, `mvn package`, `pytest`, and long smoke tests may need deliberate treatment if mew expects them to receive managed budget.
- Shell parsing complexity: compound commands with heredocs, command substitutions, aliases, functions, or wrappers can defeat simple token logic. Conservative fallback should avoid budget promotion when the invoked command cannot be identified.
- Budget semantics should not become approval semantics. Codex and Claude keep safety/approval classification separate from lifecycle/backgrounding; mew should preserve that separation.
