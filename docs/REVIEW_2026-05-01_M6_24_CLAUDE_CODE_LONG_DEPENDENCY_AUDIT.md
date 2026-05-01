# Review: Claude Code Patterns For M6.24 Long Dependency Reliability

Date: 2026-05-01

Purpose: local reference audit of `references/fresh-cli/claude-code` for transferable architecture patterns relevant to M6.24 long dependency/toolchain build reliability. This is not a benchmark-solving audit and should not be read as a recommendation to copy Claude Code behavior literally.

Codex-ultra cross-check: local audit session `019de327-6dcc-71d0-8d17-f0a182889c23`.

## Inspected Files

Claude Code:
- `references/fresh-cli/claude-code/src/constants/systemPromptSections.ts`
- `references/fresh-cli/claude-code/src/constants/prompts.ts`
- `references/fresh-cli/claude-code/src/utils/api.ts`
- `references/fresh-cli/claude-code/src/services/api/claude.ts`
- `references/fresh-cli/claude-code/src/services/api/promptCacheBreakDetection.ts`
- `references/fresh-cli/claude-code/src/Tool.ts`
- `references/fresh-cli/claude-code/src/services/tools/toolExecution.ts`
- `references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts`
- `references/fresh-cli/claude-code/src/services/tools/toolOrchestration.ts`
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx`
- `references/fresh-cli/claude-code/src/tools/BashTool/prompt.ts`
- `references/fresh-cli/claude-code/src/tools/BashTool/bashPermissions.ts`
- `references/fresh-cli/claude-code/src/types/permissions.ts`
- `references/fresh-cli/claude-code/src/hooks/useCanUseTool.tsx`
- `references/fresh-cli/claude-code/src/tools/TodoWriteTool/TodoWriteTool.ts`
- `references/fresh-cli/claude-code/src/tools/TodoWriteTool/prompt.ts`
- `references/fresh-cli/claude-code/src/tools/TaskCreateTool/prompt.ts`
- `references/fresh-cli/claude-code/src/tools/TaskUpdateTool/TaskUpdateTool.ts`
- `references/fresh-cli/claude-code/src/tools/TaskUpdateTool/prompt.ts`
- `references/fresh-cli/claude-code/src/tools/AgentTool/AgentTool.tsx`
- `references/fresh-cli/claude-code/src/tools/AgentTool/prompt.ts`
- `references/fresh-cli/claude-code/src/tools/AgentTool/runAgent.ts`
- `references/fresh-cli/claude-code/src/tools/AgentTool/forkSubagent.ts`
- `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/exploreAgent.ts`
- `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/verificationAgent.ts`
- `references/fresh-cli/claude-code/src/utils/forkedAgent.ts`
- `references/fresh-cli/claude-code/src/memdir/memdir.ts`
- `references/fresh-cli/claude-code/src/services/SessionMemory/sessionMemory.ts`
- `references/fresh-cli/claude-code/src/services/SessionMemory/sessionMemoryUtils.ts`
- `references/fresh-cli/claude-code/src/services/SessionMemory/prompts.ts`
- `references/fresh-cli/claude-code/src/services/compact/autoCompact.ts`
- `references/fresh-cli/claude-code/src/query.ts`

Mew context:
- `ROADMAP_STATUS.md`
- `docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md`
- `docs/M6_24_DECISION_LEDGER.md`
- `docs/REVIEW_2026-05-01_M6_24_MEW_LONG_DEP_DIVERGENCE.md`
- `src/mew/prompt_sections.py`
- `src/mew/work_loop.py`
- `src/mew/acceptance.py`
- `src/mew/acceptance_evidence.py`

## Reference Patterns

Claude Code separates static policy from volatile evidence aggressively. Static prompt content is built through named prompt sections, while `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` separates globally cacheable text from session-specific guidance, memory, env info, MCP instructions, scratchpad state, tool summaries, and token budget evidence. Volatile sections use explicit uncached helpers with a reason, and prompt-cache break detection records the hashes and headers that determine whether the stable prefix stayed stable.

Tool execution is a typed substrate rather than prompt convention. `Tool`, `ToolUseContext`, and `ToolPermissionContext` carry schema validation, permissions, read/write/destructive/concurrency flags, hooks, output mapping, progress, background execution, content replacement, and agent identity. Bash specifically models long-running work with timeout, background task ids, persisted raw output paths, progress polling, semantic return interpretation, and large-output storage.

Todo and task state are small but explicit: pending, in-progress, completed, one active task, no completion while partial/failing, and a structural nudge to invoke verification when a substantial task list closes without verification. This is not an authoritative done gate; it is a prompt/tool-result steering mechanism.

Memory is separated by purpose. Persistent memory is for future-session user/project preferences, not derivable repo facts or ephemeral debugging. Session memory is a bounded, structured summary updated by a constrained background agent with narrow file permissions. Compaction uses typed thresholds and circuit breakers; prompts summarize current state, errors, next steps, and files, but retries/failure counts are state.

Agents are separated by role and tool surface. Explore is read-only and omits heavy project memory. Verification is read-only for project files, can create temp probes, must run commands, and must end with `VERDICT: PASS|FAIL|PARTIAL`. Forked agents can inherit exact parent prompt bytes and tools for cache reuse, but mutable state is isolated.

Permissions live in typed policy plus hooks/classifiers. The prompt explains behavior, but allow/deny/ask, sources, working-directory scope, async-agent restrictions, and automated checks are represented as data and resolved before tool execution.

## Mew Implications

The main lesson for M6.24 is that long dependency reliability should move down a layer. Mew already took a good first step with prompt sections, but `LongDependencyProfile`, `RuntimeLinkProof`, and `RecoveryBudget` still wrap accumulated tactical prompt text. Claude Code’s transferable pattern is to keep prompts as compact contracts and let typed execution state, tool lifecycle, and verifier evidence carry the detailed recovery loop.

For compile-compcert-shaped failures, the durable mew object should not be another profile clause. It should be a generic long-build/recovery state record: source channel and authority, dependency branch selected/rejected, build cwd/target/timeout/result, produced artifacts, runtime/library proof, default invocation proof, wall budget remaining/reserved, failure class, and next allowed recovery action.

Runtime link proof belongs partly in the done gate and partly in execution state. Prompt guidance can say “compiler/toolchain outputs require runtime/default-link proof,” but the actual acceptance should consume normalized evidence records: default smoke command, artifact freshness, missing-library failure, runtime target build/install attempt, and later default-smoke success.

Recovery budget should be controller state, not prose. Claude Code’s circuit breakers and background task lifecycle suggest that mew should track repeated failed recovery classes, remaining wall budget, and final-proof reserve as first-class fields, then render only the next action to the model.

Verification should stay independent and evidence-linked. Claude Code’s verifier prompt is useful as a behavioral reference, but mew’s stronger acceptance gate should remain the authority: final status should depend on linked command/file evidence, not on whether the model wrote convincing verification prose.

## Divergence Risks

Claude Code is optimized for an interactive commercial CLI with prompt-cache economics, feature gates, MCP/plugin churn, telemetry, teammate modes, and UI permissions. Copying that machinery wholesale would add surface area without solving M6.24.

The verification nudge is heuristic. Mew should not copy “3+ tasks without a verification task” as a done condition. It should keep deterministic finish gating based on evidence refs, freshness, and artifact/runtime proof.

Do not copy prompt content literally. The importable part is the boundary discipline: stable contracts, dynamic evidence, typed tool state, constrained verifier roles, and explicit failure/circuit-breaker state.

Do not move benchmark-specific solver knowledge into memory. Claude Code’s memory taxonomy explicitly excludes derivable repo/debug details; mew should avoid turning compile-compcert tactics into durable memory that contaminates unrelated long dependency tasks.

Do not let backgrounding hide proof. Claude Code’s background commands and agents reduce context pressure, but M6.24 still needs explicit final artifact and default runtime/link evidence before finish.

## Concrete Import Candidates

High:
- Promote long dependency execution into a typed `LongBuildState` / recovery ledger instead of extending `LongDependencyProfile`.
- Add an explicit static/dynamic prompt boundary for mew work prompts: static implementation policy and profiles first, dynamic resume/evidence/context last, with cache-break reasons for volatile sections.
- Represent `RuntimeLinkProof` as normalized evidence consumed by `acceptance_done_gate_decision()`, not primarily as prompt guidance.
- Make `RecoveryBudget` controller-owned: wall budget, reserve, failure class counts, and next permitted recovery action.
- Keep verifier separation, but require verifier output to cite commands and feed mew’s existing evidence refs rather than replacing them.

Medium:
- Add long-running command lifecycle fields modeled after Claude Code’s Bash output: background id, persisted output path, interrupted/timed-out/backgrounded flags, semantic return interpretation, and progress snapshots.
- Use role-specific explorer/verifier tool surfaces: read-only explorer, read-only project verifier with temp probes, implementation lane with write tools.
- Add bounded session-memory style summaries for long work: current state, errors/corrections, artifacts, commands, next action, and verifier state, with per-section size limits.
- Add prompt-cache break metrics around work prompt sections to reveal accidental dynamic text in static profiles.

Low:
- Exact prompt-cache reuse for forked agents. Useful later if mew has measurable cache pressure, but not central to long dependency reliability.
- Claude Code’s agent frontmatter, MCP loading, teammate/swarm, remote isolation, telemetry, and feature-flag latches.
- Permission classifier complexity. Mew needs typed policy and safe shell constraints, not Claude Code’s full classifier stack.

## Bottom Line

Mew should stop treating each compile-compcert miss as a reason to append another long-dependency sentence. The reference architecture points toward a smaller prompt, a richer typed long-build state, explicit recovery transitions, and an evidence-linked verifier/done gate. Keep the current M6.24 acceptance evidence strength; move tactical long dependency recovery out of prose and into durable execution state.
