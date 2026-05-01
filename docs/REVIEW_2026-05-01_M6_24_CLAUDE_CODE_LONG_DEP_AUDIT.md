# REVIEW 2026-05-01: M6.24 Claude Code Long Dependency Audit

Source inspected: `references/fresh-cli/claude-code`

Inspection model: `codex-ultra` session `019de325-7ef2-79b2-bb1d-b59b8ac3c78b`

## Executive Conclusion

Material divergence: **medium**.

Mew M6.24 is not conceptually far from Claude Code: it already has named prompt sections, long-dependency build state, recovery budget work, acceptance evidence, and a one-authoritative-lane architecture. The divergence is substrate depth. Claude Code stabilizes long and failure-prone work mostly through reusable tool, task, permission, prompt-cache, progress, and recovery primitives; mew's current M6.24 repair still carries too much of the behavior in accumulating detector/resume/profile clauses around `LongDependencyProfile`, `RuntimeLinkProof`, and `RecoveryBudget`.

That is not a reason to copy Claude Code wholesale. It is a reason to stop treating every `compile-compcert` miss as another profile sentence until the long-running command/evidence substrate is stronger.

## Claude Code Patterns Found

### Tool Execution And Streaming

- **Durable architecture:** tools declare runtime properties, not just natural-language instructions: `isConcurrencySafe`, `isReadOnly`, `isDestructive`, `interruptBehavior`, schemas, validation, permission checks, progress rendering, and result size limits in `references/fresh-cli/claude-code/src/Tool.ts:123`, `references/fresh-cli/claude-code/src/Tool.ts:362`, and `references/fresh-cli/claude-code/src/Tool.ts:743`.
- **Durable architecture:** tool orchestration partitions read-only/concurrency-safe work from exclusive work, and bounded concurrent execution is centralized in `references/fresh-cli/claude-code/src/services/tools/toolOrchestration.ts:19` and `references/fresh-cli/claude-code/src/services/tools/toolOrchestration.ts:152`.
- **Durable architecture:** `StreamingToolExecutor` starts safe tool calls while the assistant is still streaming, serializes unsafe calls, emits progress early, preserves result order, and synthesizes error results for abort/fallback paths. See `references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts:34`, `references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts:153`, `references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts:265`, and `references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts:412`.
- **Prompt heuristic:** the model is told how to use tools, but reliability does not depend only on those instructions. Transcript pairing and fallback recovery are enforced by `references/fresh-cli/claude-code/src/query.ts:826`, `references/fresh-cli/claude-code/src/query.ts:1011`, and `references/fresh-cli/claude-code/src/query.ts:1366`.

### Long-Running Tasks

- **Durable architecture:** Bash supports explicit background execution, progress callbacks, timeout handling, output persistence, and foreground-to-background transitions. See `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:223`, `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:624`, `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:728`, `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:965`, and `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:1027`.
- **Durable architecture:** local shell tasks have task ids, completion notifications, output file paths, cleanup, and a stalled interactive-prompt watchdog. See `references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:22`, `references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:105`, `references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:180`, and `references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:293`.
- **Durable architecture:** background output retrieval is a read-only task interface with blocking/nonblocking modes in `references/fresh-cli/claude-code/src/tools/TaskOutputTool/TaskOutputTool.tsx:30`, `references/fresh-cli/claude-code/src/tools/TaskOutputTool/TaskOutputTool.tsx:117`, and `references/fresh-cli/claude-code/src/tools/TaskOutputTool/TaskOutputTool.tsx:144`.
- **Prompt heuristic:** Bash prompt text still guides the model away from sleeps/polling and toward monitor/background usage, but the core support is the task/runtime layer.

### Todo And Planning

- **Durable architecture:** `TodoWrite` is a structured state tool, session/agent scoped, deferred, permissionless, and able to nudge verification when a multi-item plan is closed without a verification task. See `references/fresh-cli/claude-code/src/tools/TodoWriteTool/TodoWriteTool.ts:31`, `references/fresh-cli/claude-code/src/tools/TodoWriteTool/TodoWriteTool.ts:65`, and `references/fresh-cli/claude-code/src/tools/TodoWriteTool/TodoWriteTool.ts:72`.
- **Prompt heuristic:** the todo prompt describes when to use pending/in-progress/completed states in `references/fresh-cli/claude-code/src/tools/TodoWriteTool/prompt.ts:3` and `references/fresh-cli/claude-code/src/tools/TodoWriteTool/prompt.ts:144`; that is local model guidance over a real state primitive.

### Prompt Sections And Cacheability

- **Durable architecture:** static prompt sections are memoized, uncached dynamic sections must declare a reason, and prompt state is cleared on `/clear` and `/compact`. See `references/fresh-cli/claude-code/src/constants/systemPromptSections.ts:16`, `references/fresh-cli/claude-code/src/constants/systemPromptSections.ts:27`, and `references/fresh-cli/claude-code/src/constants/systemPromptSections.ts:60`.
- **Durable architecture:** the system prompt has an explicit static/dynamic boundary for cross-org cacheable content, and API request code maps pre-boundary blocks to cache scopes. See `references/fresh-cli/claude-code/src/constants/prompts.ts:105`, `references/fresh-cli/claude-code/src/constants/prompts.ts:491`, `references/fresh-cli/claude-code/src/constants/prompts.ts:560`, `references/fresh-cli/claude-code/src/utils/api.ts:321`, and `references/fresh-cli/claude-code/src/services/api/claude.ts:3213`.
- **Durable architecture:** built-in tools are kept in a stable prefix before MCP tools to preserve cache stability in `references/fresh-cli/claude-code/src/tools.ts:345`.
- **Prompt heuristic:** model-facing prompt sections still contain behavioral advice; the architectural part is the section registry, static/dynamic split, cache scope, and churn discipline.

### Permission And Tool Policy

- **Durable architecture:** permission context is typed and carries mode, allow/deny/ask rules by source, bypass state, additional directories, and prompt-avoidance flags in `references/fresh-cli/claude-code/src/Tool.ts:123` and `references/fresh-cli/claude-code/src/types/permissions.ts:16`.
- **Durable architecture:** policy evaluation orders deny/ask/allow, handles headless contexts, bypass-immune checks, classifier fallback, denial tracking, and fail-closed paths. See `references/fresh-cli/claude-code/src/utils/permissions/permissions.ts:122`, `references/fresh-cli/claude-code/src/utils/permissions/permissions.ts:392`, `references/fresh-cli/claude-code/src/utils/permissions/permissions.ts:518`, and `references/fresh-cli/claude-code/src/utils/permissions/permissions.ts:1158`.
- **Durable architecture:** Bash-specific matching uses exact and prefix rules plus path constraints before allowing commands in `references/fresh-cli/claude-code/src/tools/BashTool/bashPermissions.ts:937` and `references/fresh-cli/claude-code/src/tools/BashTool/bashPermissions.ts:1050`.
- **Prompt heuristic:** the exact classifier wording and explanatory permission prompt text are local choices; the durable concept is policy as data plus fail-closed enforcement.

### Explore And Verifier Separation

- **Durable architecture:** Explore is a separate read-only agent with write tools disallowed and heavyweight project context omitted. See `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/exploreAgent.ts:13` and `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/exploreAgent.ts:64`.
- **Durable architecture:** Verification is a separate adversarial agent, forbids project modifications, requires exact command output, and must end with a verdict. See `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/verificationAgent.ts:10`, `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/verificationAgent.ts:71`, and `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/verificationAgent.ts:117`.
- **Durable architecture:** subagent execution has scoped tools, permission overrides, sidechain transcript recording, async isolation, and cleanup in `references/fresh-cli/claude-code/src/tools/AgentTool/runAgent.ts:385`, `references/fresh-cli/claude-code/src/tools/AgentTool/runAgent.ts:412`, `references/fresh-cli/claude-code/src/tools/AgentTool/runAgent.ts:697`, and `references/fresh-cli/claude-code/src/tools/AgentTool/runAgent.ts:732`.
- **Prompt heuristic:** the exact Explore and Verifier wording is not the reusable part. The reusable part is role separation backed by tool restrictions, evidence-only outputs, and non-authoritative helper lanes.

### Recovery From Tool Errors, Timeouts, And Fallbacks

- **Durable architecture:** unknown tools, schema errors, validation errors, permission denial, tool exceptions, and post-tool hook failures become model-visible `tool_result` errors rather than breaking transcript invariants. See `references/fresh-cli/claude-code/src/services/tools/toolExecution.ts:337`, `references/fresh-cli/claude-code/src/services/tools/toolExecution.ts:599`, `references/fresh-cli/claude-code/src/services/tools/toolExecution.ts:682`, `references/fresh-cli/claude-code/src/services/tools/toolExecution.ts:916`, and `references/fresh-cli/claude-code/src/services/tools/toolExecution.ts:1589`.
- **Durable architecture:** query recovery has guarded transitions for streaming fallback, prompt-too-long compacting, max-output-token continuation, aborts, missing tool result synthesis, stop-hook loop avoidance, and recursive continuation. See `references/fresh-cli/claude-code/src/query.ts:592`, `references/fresh-cli/claude-code/src/query.ts:712`, `references/fresh-cli/claude-code/src/query.ts:980`, `references/fresh-cli/claude-code/src/query.ts:1062`, `references/fresh-cli/claude-code/src/query.ts:1185`, `references/fresh-cli/claude-code/src/query.ts:1258`, and `references/fresh-cli/claude-code/src/query.ts:1715`.
- **Prompt heuristic:** resume messages and continuation nudges are local prompt choices. The durable concept is explicit recovery state and transcript-preserving fallback.

## High-Level Comparison To Mew M6.24

Mew has already adopted part of the Claude Code shape:

- Mew's prompt section registry records ids, versions, hashes, stability, cache policy, and cache hints in `src/mew/prompt_sections.py:20` and `src/mew/prompt_sections.py:86`.
- Normal work THINK prompts are split into `ImplementationLaneBase`, `SourceAcquisitionProfile`, `LongDependencyProfile`, `RuntimeLinkProof`, `RecoveryBudget`, `CompactRecovery`, `DynamicFailureEvidence`, schema, and context JSON in `src/mew/work_loop.py:6300`, `src/mew/work_loop.py:6370`, `src/mew/work_loop.py:6380`, `src/mew/work_loop.py:6391`, and `src/mew/work_loop.py:6415`.
- Long dependency progress and strategy blockers are structured into `long_dependency_build_state` in `src/mew/work_session.py:5486`, `src/mew/work_session.py:5527`, `src/mew/work_session.py:5670`, and surfaced in resume text at `src/mew/work_session.py:10394`.
- Artifact acceptance proof is becoming deterministic and command-backed in `src/mew/acceptance_evidence.py:462`, `src/mew/acceptance_evidence.py:514`, and `src/mew/acceptance_evidence.py:665`.
- Tool wall-clock budget and long-build recovery reserve exist in `src/mew/commands.py:6154` and `src/mew/commands.py:6204`.

The active dossier also names the central risk directly: `prompt_profile_accretion_risk` after many detector/profile repairs around long dependency tasks in `docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md:179`. The decision ledger shows the same repair sequence repeatedly adding named blockers and guidance for `compile-compcert` failures in `docs/M6_24_DECISION_LEDGER.md:70`, `docs/M6_24_DECISION_LEDGER.md:89`, `docs/M6_24_DECISION_LEDGER.md:138`, and `docs/M6_24_DECISION_LEDGER.md:169`.

The main difference is that Claude Code does not appear to solve long builds through a large task-family-specific profile. It provides generic substrate: long command progress, background tasks, output files, transcript-safe tool results, cache-stable prompt sections, permission policy, and evidence-only helper agents. Mew's M6.24 approach is moving in that direction, but the current center of gravity is still a growing list of long-dependency blockers plus natural-language profile text.

## What Mew Should Adopt Now

- Define a minimal `LongRunningCommand` or `ToolResultEvidence` record for work sessions: tool id, command, cwd, start/end time, exit code, timed out, timeout seconds, output path, progress tail, artifact refs, and post-proof mutation guard.
- Move more of `RecoveryBudget` into runner enforcement. Mew already caps long tool timeouts; the next step is making remaining wall budget, recovery reserve, and continuation eligibility first-class evidence in the work-session state instead of mostly profile guidance.
- Treat `RuntimeLinkProof` as a typed acceptance contract: default invocation smoke, no custom runtime path flags for final proof, runtime library build/install evidence, exact artifact path, and explicit command ids.
- Add a small task/progress registry for long `run_command` work before attempting a full Claude-style streaming executor. The important near-term features are task id, output file, completion notification, timeout status, and interactive-stall detection.
- Keep future long-dependency prompt changes inside named prompt sections and track accretion with section char deltas, section hash churn, blocker count, stale-blocker rate, and speed/proof delta.
- Define read-only Explorer and adversarial Verifier helper contracts as evidence-only lanes, matching `docs/DESIGN_2026-04-26_RESIDENT_LANE_ARCHITECTURE.md`; they must not become second authoritative implementation lanes.

## What Mew Should Defer

- Full Claude Code streaming tool execution. It is valuable, but too large for the current `compile-compcert` close gate.
- Full subagent/swarm/task framework and remote worktree agents.
- Claude Code's auto permission classifier and interactive permission UX.
- Exact Claude Code prompt text for Explore, Verifier, Bash, or Todo. Mew should adopt the role/tool-policy concepts, not the local wording.
- MCP tool search, hooks, status-line polish, and prompt-cache beta mechanics unless a separate mew milestone calls for them.

## Risks Of Continuing Detector And Profile Accretion

- A sequence of individually generic detectors can become an implicit `compile-compcert` solver.
- Regex-heavy artifact proof can accumulate false positives and false negatives faster than same-shape reruns expose them.
- New blockers can preserve stale state or outrank a narrower later blocker unless clearing and priority rules stay carefully tested.
- Long prompt/profile text competes with compact recovery and cache stability, especially under wall-clock pressure.
- The model may learn to satisfy blocker wording instead of preserving real build state and external acceptance evidence.
- Acceptance evidence can drift from "direct command-backed proof" into a specialized semantic parser for one benchmark family.

## Concrete Next Investigation And Design Questions

1. What is the smallest command evidence schema that can replace most long-dependency shell-output regex interpretation?
2. Which current long-dependency blockers collapse into three to five typed contracts: source provenance, branch choice, build continuation, runtime link proof, and final artifact proof?
3. Should `RecoveryBudget` be evaluated before the model chooses an action, before the tool runs, or both?
4. What task/progress fields are needed so a timed-out long build can resume from output and state rather than from prompt memory?
5. What metric should gate additional profile text: prompt-section char delta, blocker count, stale-blocker rate, speed_1 result, proof_5 result, or a composite?
6. Can an evidence-only verifier/explorer helper catch the current runtime-link misses without weakening the one-authoritative-lane rule?
7. What is the canonical default-link proof shape for compiler/toolchain tasks, and how should custom-path diagnostic smokes be recorded without counting as final acceptance?
