# Claude Code Acceptance Patterns for mew

Date: 2026-05-01

Source inspected: `/Users/mk/dev/tech_check/claude-code`

Target: mew implementation lane acceptance, done-gate, verifier, evidence, and permission design.

Constraint followed: Claude Code was inspected read-only. This report changes only the mew docs tree.

## Files and Lines Inspected

### Todo and Task Completion Semantics

- `src/utils/todo/types.ts:4-18`: Todo state is intentionally small: `pending`, `in_progress`, `completed`, plus `content` and `activeForm`. There is no acceptance, evidence, verifier, or completion-attempt record.
- `src/tools/TodoWriteTool/TodoWriteTool.ts:65-87`: completed todos are cleared from state when all are done; the tool also nudges verification when 3+ tasks are closed without a verification-related task.
- `src/tools/TodoWriteTool/TodoWriteTool.ts:104-108`: Todo completion can trigger a verification-agent reminder, and the implementation agent is explicitly told it cannot self-assign `PARTIAL`.
- `src/tools/TodoWriteTool/prompt.ts:144-170`: exactly one task should be `in_progress`; completed tasks should be marked immediately, and tasks must not be marked completed if tests fail, implementation is partial, errors remain, or dependencies are missing.
- `src/utils/tasks.ts:69-87`: Task v2 adds `blocks`, `blockedBy`, `owner`, and `metadata`, but still no first-class acceptance or evidence fields.
- `src/utils/tasks.ts:94-108` and `src/utils/tasks.ts:279-307`: task-list updates use lock files and high-water marks for concurrent creation.
- `src/hooks/useTaskListWatcher.ts:70-83`, `src/hooks/useTaskListWatcher.ts:191-220`: teammate automation waits for the current task to become `completed`; available work requires pending status, no owner, and all blockers completed.
- `src/hooks/useTasksV2.ts:123-171`: all-completed task lists are hidden only after a delay and a re-read confirms they are still completed.
- `src/tools/TaskListTool/TaskListTool.ts:72-83`: completed blockers are filtered out of `blockedBy` in the model-facing task list.
- `src/tools/TaskListTool/prompt.ts:17-48`: agents should call `TaskList`, work in ID order, and avoid stealing owned tasks.
- `src/tools/TaskUpdateTool/prompt.ts:7-20`: task completion rules repeat the hard negatives: failing tests, partial work, unresolved errors, or missing dependencies mean not completed.
- `src/tools/TaskUpdateTool/prompt.ts:47-50`: a stale task view should be refreshed with `TaskGet` before updating.
- `src/tools/TaskUpdateTool/TaskUpdateTool.ts:185-199`: setting a task to `in_progress` auto-assigns the current agent as owner.
- `src/tools/TaskUpdateTool/TaskUpdateTool.ts:229-264`: `TaskCompleted` hooks run before a task is actually marked `completed`; blocking hook errors prevent completion.
- `src/tools/TaskUpdateTool/TaskUpdateTool.ts:326-349` and `src/tools/TaskUpdateTool/TaskUpdateTool.ts:384-397`: closing several tasks without verification triggers a model-facing verifier reminder.

### Acceptance and Done Gates

- `src/query/stopHooks.ts:175-331`: Stop hooks run after model output; blocking hook feedback is converted into model input so the same query can continue.
- `src/query/stopHooks.ts:334-455`: teammate completion runs `TaskCompleted` hooks for owned in-progress tasks after Stop hooks pass; blocking/prevent-continuation handling is reused.
- `src/query.ts:1258-1305`: stop hooks are skipped after API errors, and blocking stop-hook feedback is appended as user messages with a `stop_hook_blocking` transition.
- `src/utils/hooks.ts:500-543`: hook JSON can block continuation with `continue: false` or `decision: "block"`.
- `src/utils/hooks.ts:580-620`: hook responses validate event names; `PreToolUse` can return permission decisions, updated input, and additional context.
- `src/utils/hooks.ts:710-725`: hook success/blocking messages become attachments for traceability.
- `src/utils/hooks.ts:1894-1928`: Stop and TaskCompleted hook feedback is formatted as model-readable blocking feedback.
- `src/utils/hooks.ts:3775-3817`: `executeTaskCompletedHooks` passes task id, subject, description, teammate, and team metadata; blocking hooks block task completion.

### Plan Approval and Done Conditions

- `src/tools/EnterPlanModeTool/prompt.ts:4-12`: plan mode is for exploration, design, presenting a plan for approval, clarifying, and exiting plan mode.
- `src/tools/EnterPlanModeTool/prompt.ts:23-64` and `src/tools/EnterPlanModeTool/prompt.ts:108-136`: prompt variants distinguish broad planning from stricter ambiguity handling.
- `src/tools/EnterPlanModeTool/prompt.ts:95-97` and `src/tools/EnterPlanModeTool/prompt.ts:160-163`: implementation must not start until the user approves the plan.
- `src/tools/ExitPlanModeTool/prompt.ts:6-22`: exit only after a plan file is written and the plan is complete and unambiguous.
- `src/tools/ExitPlanModeTool/ExitPlanModeV2Tool.ts:168-238`: the tool is disabled in incompatible channel modes, validates plan mode, and requires `ask` permission for non-teammates.
- `src/tools/ExitPlanModeTool/ExitPlanModeV2Tool.ts:481-489`: an approved plan is echoed back with the plan file path and instruction to start coding and update todos.
- `src/utils/messages.ts:3156-3188`: final plan variants require critical files, reuse of existing utilities with file/line references, and a verification section with a single command.
- `src/utils/messages.ts:3227-3231`: plan mode is read-only except the plan file.
- `src/utils/messages.ts:3286-3290`: plan-mode turns must end with `AskUserQuestion` or `ExitPlanMode`.
- `src/utils/messages.ts:3331-3378`: iterative planning is complete when it explains what to change, files involved, reuse strategy, and verification.
- `src/components/permissions/ExitPlanModePermissionRequest/ExitPlanModePermissionRequest.tsx:200-217` and `src/components/permissions/ExitPlanModePermissionRequest/ExitPlanModePermissionRequest.tsx:454-507`: approval loads/edits the plan and can change permission mode; rejection keeps plan mode and carries feedback.

### Tool Evidence and Verifier Grounding

- `src/constants/prompts.ts:211`: before reporting completion, the agent should run tests/scripts/checks and report inability to verify.
- `src/constants/prompts.ts:237-240`: final reporting must not claim tests passed if they failed or were not run.
- `src/constants/prompts.ts:390-395`: non-trivial implementation requires independent adversarial verification; only the verifier assigns the verdict, and PASS requires spot-checked command output.
- `src/tools/AgentTool/built-in/verificationAgent.ts:10-22`: verifier role is adversarial, read-only for project files, and not an implementation confirmer.
- `src/tools/AgentTool/built-in/verificationAgent.ts:27-72`: verifier strategy requires repo baseline reading, actual command execution, adversarial probes, and no rationalized PASS from static reading alone.
- `src/tools/AgentTool/built-in/verificationAgent.ts:74-129`: verifier output must include exact command, observed output, result, and end exactly with `VERDICT: PASS`, `VERDICT: FAIL`, or `VERDICT: PARTIAL`.
- `src/tools/AgentTool/built-in/verificationAgent.ts:131-152`: verifier use cases and disallowed tools include `Edit`, `Write`, `NotebookEdit`, `Agent`, and `ExitPlanMode`.
- `src/tools/AgentTool/prompt.ts:80-139`: delegated agents need scoped prompts, file paths, line references, concrete checks, and no fabricated results.
- `src/tools/AgentTool/prompt.ts:255-271`: background agents notify when done; foreground only when the next step depends on the result.
- `src/services/tools/toolExecution.ts:775-860`: observable input, PreToolUse hooks, updated inputs, and prevent-continuation paths are captured before execution.
- `src/services/tools/toolExecution.ts:916-1045`: permission denial returns an error tool result before tool execution.
- `src/services/tools/toolExecution.ts:1207-1295`: tool execution traces file diffs, bash output, and mapped result data.
- `src/services/tools/toolExecution.ts:1397-1588`: PostToolUse hooks can modify output; final messages include permission feedback and hook-stopped continuation records.
- `src/services/tools/toolOrchestration.ts:26-116`: tool calls are batched conservatively; read-only/concurrency-safe calls can run concurrently, unsafe or parse-failed calls serialize.
- `src/constants/toolLimits.ts:5-49`, `src/utils/toolResultStorage.ts:131-198`, and `src/utils/toolResultStorage.ts:272-333`: large results are persisted with previews and paths; empty results are made explicit as completed-with-no-output.
- `src/utils/toolResultStorage.ts:786-905`: per-message budgets persist largest fresh outputs and reapply cached replacements atomically.
- `src/tools/BashTool/BashTool.tsx:555-620`: Bash results preserve stdout, stderr, background status, output-file path, and persisted-output metadata.

### Permission and Approval Gates

- `src/Tool.ts:123-138`: tool permission context carries mode, allow/deny/ask rules, bypass availability, auto availability, stripped dangerous rules, and prompt-avoidance flags.
- `src/Tool.ts:484-503` and `src/Tool.ts:744-770`: input validation precedes permission checks; default tool permission is permissive unless a tool overrides it.
- `src/utils/permissions/PermissionMode.ts:42-90`: permission modes include `default`, `plan`, `acceptEdits`, `bypassPermissions`, `dontAsk`, and ant-only `auto`.
- `src/hooks/useCanUseTool.tsx:32-168`: allow resolves immediately, deny resolves without UI, ask can route through hooks/classifier/teammate forwarding/interactive permission.
- `src/hooks/toolPermission/PermissionContext.ts:63-94`: resolve-once prevents permission race double-resolution.
- `src/hooks/toolPermission/PermissionContext.ts:139-173`: permission updates persist and aborts/cancellations produce a controlled decision.
- `src/hooks/toolPermission/PermissionContext.ts:216-318`: `PermissionRequest` hooks can allow/deny, and user approval can persist rule updates and carry feedback.
- `src/hooks/toolPermission/handlers/interactiveHandler.ts:43-203`: interactive permission races hooks, classifier, and user response with resolve-once semantics.
- `src/hooks/toolPermission/handlers/swarmWorkerHandler.ts:26-146`: workers use classifier, leader forwarding, and pending indicators; callbacks are registered before sending to avoid races.
- `src/hooks/toolPermission/handlers/coordinatorHandler.ts:16-61`: coordinators wait for hooks and classifier before showing interactive UI.
- `src/utils/permissions/permissions.ts:473-548`: `dontAsk` converts ask to deny; auto mode classifier handling excludes non-classifier-approvable checks.
- `src/utils/permissions/permissions.ts:560-686`: PowerShell, accept-edits fast paths, and safe allowlisted tools have explicit mode handling.
- `src/utils/permissions/permissions.ts:688-952`: classifier decisions are logged, failures are handled with explicit fail-open/fail-closed behavior, and headless/background asks auto-deny after hooks.
- `src/utils/permissions/permissionSetup.ts:85-125`, `src/utils/permissions/permissionSetup.ts:268-341`, and `src/utils/permissions/permissionSetup.ts:469-553`: dangerous broad rules are detected and stripped before auto mode.
- `src/utils/permissions/permissionSetup.ts:582-790`: mode transitions, bypass availability, remote-mode limits, and initial-mode precedence are centralized.
- `src/utils/permissions/permissionSetup.ts:930-984`, `src/utils/permissions/permissionSetup.ts:1068-1148`, and `src/utils/permissions/permissionSetup.ts:1441-1490`: auto-mode gate access avoids stale async clobbering and plan mode can stash/restore pre-plan mode.

### Shell and File Safety Details

- `src/tools/BashTool/prompt.ts:64-110`, `src/tools/BashTool/prompt.ts:228-250`, and `src/tools/BashTool/prompt.ts:303-333`: commit and bash protocol requires status/diff/log checks, no skipped hooks, careful sandbox escalation, no polling sleep loops, and parent-dir verification.
- `src/tools/BashTool/readOnlyValidation.ts:125-128`, `src/tools/BashTool/readOnlyValidation.ts:1230-1250`, and `src/tools/BashTool/readOnlyValidation.ts:1876-1990`: read-only command validation is syntax-aware and fails closed on write/network/ambiguous behavior.
- `src/tools/BashTool/pathValidation.ts:594-655` and `src/tools/BashTool/pathValidation.ts:1013-1109`: `mv`/`cp` flags, compound `cd` plus writes, process substitution, and shell expansion require manual approval.
- `src/tools/BashTool/bashPermissions.ts:1088-1165`: deny/ask rules are evaluated before path constraints; exact allow, mode, read-only, and prompts are later fallbacks.
- `src/tools/BashTool/bashPermissions.ts:1661-1740`, `src/tools/BashTool/bashPermissions.ts:2200-2311`, and `src/tools/BashTool/bashPermissions.ts:2314-2385`: AST parsing/shadow paths detect injection, compound `cd` plus git asks, original redirections are validated, and dangerous subcommands are not hidden behind path asks.
- `src/tools/BashTool/bashPermissions.ts:2472-2510`: synthesized exact permission suggestions keep the UI label honest when a safety check asks.
- `src/tools/BashTool/BashTool.tsx:434-467` and `src/tools/BashTool/BashTool.tsx:524-540`: Bash is concurrency-safe only when read-only; hook matching fails safe for complex commands and validates blocked sleep patterns.
- `src/utils/permissions/filesystem.ts:53-79`, `src/utils/permissions/filesystem.ts:1219-1335`: sensitive files and deny rules are protected before allow/safety checks; safety asks carry reasons and classifier eligibility.
- `src/tools/FileEditTool/FileEditTool.ts:442-455` and `src/tools/FileWriteTool/FileWriteTool.ts:266-305`: edit/write tools reject stale writes and preserve model-specified line endings.

### Test Surface Observed

- No dedicated test tree was present in this checkout. `rg --files` showed no `test`, `spec`, or `__tests__` suite other than source files whose names contain words like `specs` or `hit-test`. The test plan below is therefore inferred from source invariants and comments, not copied from an existing test suite.

## Transferable Concepts

1. Make completion a guarded state transition, not just a prompt convention.
   - Claude Code prompts say when not to mark done, but the stronger pattern is `TaskCompleted` hooks blocking `completed`.
   - mew should move this into a `completeTask()` command that reloads latest state, validates blockers, validates acceptance/evidence, runs hooks, records the attempt, and only then mutates status.

2. Store acceptance and evidence in the task model.
   - Claude Code task/todo state is intentionally lean; mew needs more durable lane semantics.
   - Add `acceptance[]`, `requiredEvidence[]`, `evidenceIds[]`, `verifierRequirement`, `verifierVerdict`, and `completionAttempts[]`.

3. Feed blocker feedback back to the agent as structured next input.
   - Stop and TaskCompleted hooks do not just fail silently; they become model-readable blocking feedback.
   - mew should return a typed `CompletionBlocked` result with actionable reasons and evidence gaps, then continue the implementation lane with that as input.

4. Treat plan approval as a mode boundary.
   - The useful import is not the UI, but the invariant: planning is read-only except a plan artifact, exit requires approval, and the approved plan becomes the implementation contract.
   - mew should require plan artifacts to include files, reuse points, acceptance criteria, and verification commands before implementation starts.

5. Persist tool evidence separately from conversational text.
   - Claude Code keeps tool results, stores oversized outputs with previews/paths, and turns empty output into explicit text.
   - mew should create immutable `ToolRunRecord` entries with command/tool input, exit status, stdout/stderr preview, persisted output path, timestamp, and task id.

6. Make verifier output parseable and adversarial.
   - The verifier prompt's most transferable rule is strict output shape: each check has exact command, observed output, and result; final verdict is exactly `PASS`, `FAIL`, or `PARTIAL`.
   - mew should parse verifier reports and reject PASS when checks lack command/output evidence.

7. Permission gates need deterministic ordering.
   - The strongest reusable pattern is deny/ask before path constraints, exact allow after safety checks, and headless asks becoming denies unless hooks decide.
   - mew should expose decision reasons and make prompt-avoidance an explicit lane policy.

8. Concurrency should derive from tool safety, not model confidence.
   - Claude Code batches read-only/concurrency-safe tools and serializes unsafe or parse-failed calls.
   - mew should classify each tool call before scheduling and fail closed when classification fails.

9. Final reporting must be evidence-bound.
   - Claude Code prompts ban claiming tests passed when they were not run.
   - mew can enforce this mechanically: final status text may reference only evidence records with successful status, or it must say verification was skipped/failed/partial.

## What Not to Copy

- Do not copy all-done todo clearing. mew needs durable completed-task and evidence history for implementation lanes.
- Do not use substring heuristics like `/verif/i` as a real done gate. Use structured verifier tasks, verifier requirements, or evidence records.
- Do not copy prompt-only completion semantics. Prompts help, but mew should enforce completion in state transitions.
- Do not copy the default permissive tool permission behavior from `Tool.ts`; mutating mew tools should require explicit policy.
- Do not import the full Ant/A-B prompt-variant and feature-gate matrix. Extract stable invariants only.
- Do not let plan approval silently switch into a broad bypass mode unless mew has an equivalent audited policy gate and visible user choice.
- Do not import the entire Bash permission stack unless mew executes shell commands. If it does, isolate it as a shell-safety module with tests around the dangerous edge cases.
- Do not treat static reading as verification for runtime claims. It can support analysis, but PASS should require executed checks unless the criterion is explicitly non-runtime.

## Suggested mew Design and Import Plan

### 1. Add Acceptance and Evidence Types

```ts
type EvidenceStatus = "passed" | "failed" | "blocked" | "skipped";

type EvidenceRecord = {
  id: string;
  taskId: string;
  kind: "command" | "tool" | "verifier" | "manual";
  toolName?: string;
  command?: string;
  inputDigest?: string;
  exitCode?: number;
  status: EvidenceStatus;
  outputPreview: string;
  outputPath?: string;
  startedAt: string;
  completedAt: string;
};

type AcceptanceCriterion = {
  id: string;
  text: string;
  requiredEvidenceKinds: EvidenceRecord["kind"][];
  satisfiedBy: string[];
};

type CompletionAttempt = {
  id: string;
  taskId: string;
  attemptedAt: string;
  result: "completed" | "blocked";
  blockingReasons: string[];
  evidenceIds: string[];
  verifierVerdict?: "PASS" | "FAIL" | "PARTIAL";
};
```

### 2. Implement a Hard `completeTask()` Gate

Order the gate as:

1. Re-read the latest task and lane state.
2. Reject stale updates or owner mismatch.
3. Require all blockers completed.
4. Require all acceptance criteria satisfied by evidence records.
5. Require required checks to have non-skipped, non-failed evidence.
6. If the task is non-trivial, require verifier verdict `PASS`; allow `PARTIAL` only when policy says environmental partials can close and final reporting must say partial.
7. Run completion hooks.
8. Persist `CompletionAttempt`.
9. Only then set `status = "completed"`.

If any step blocks, keep the task `in_progress`, persist a blocked attempt, and feed the reasons back into the implementation lane as the next model input.

### 3. Wrap Tool Execution With Evidence Capture

- Every command/tool run emits an immutable `EvidenceRecord`.
- Empty stdout/stderr becomes an explicit preview such as `(tool completed with no output)`.
- Large output is stored under a run artifact path and referenced by preview plus `outputPath`.
- Evidence records include task id and lane id so final reporting can cite them without scraping chat text.
- Tool output redaction should happen before persistence when secrets can appear.

### 4. Add a Verifier Role Contract

- Verifier can read project files and run commands, but cannot edit project files.
- Temporary scripts are allowed only under a verifier temp directory and must be recorded as evidence.
- Output parser requires:
  - one or more checks,
  - exact command/tool used for each check,
  - observed output or output artifact path,
  - per-check result,
  - final line exactly `VERDICT: PASS`, `VERDICT: FAIL`, or `VERDICT: PARTIAL`.
- PASS is rejected if any claimed check lacks evidence.
- FAIL feeds actionable findings back into implementation and prevents completion.

### 5. Turn Plan Approval Into an Implementation Contract

Require an approved plan artifact with these sections before the implementation lane starts:

- `Files`: concrete files/modules likely to change.
- `Reuse`: existing functions/utilities/patterns to reuse, with file/line references when available.
- `Acceptance`: explicit done conditions.
- `Verification`: exact command(s) or verifier checks required.
- `Risk`: permissions, shell/file writes, migrations, or user-visible behavior that require explicit approval.

Plan rejection should keep the lane in plan mode and attach the user's feedback to the next planning turn.

### 6. Add Permission Policy Ordering

For mutating tools, use this decision order:

1. Explicit deny rules.
2. Explicit ask rules and safety checks.
3. Sensitive path/resource checks.
4. Exact allow rules.
5. Mode-specific allow rules.
6. Read-only/concurrency-safe fast path.
7. Prompt/user/hook/classifier decision.
8. Headless fallback deny.

Each result should carry `decision`, `reason`, `rule`, `resource`, and whether the decision is persistable.

### 7. Add Evidence-Bound Final Reporting

Before the implementation lane can report done:

- require all active tasks completed or explicitly deferred,
- require no blocked completion attempts unresolved,
- require verifier PASS for non-trivial tasks,
- require final text to cite evidence ids or tool-run ids for test/build claims,
- downgrade final status if checks were skipped, failed, or only partially verified.

## Tests mew Should Add

1. `completeTask` rejects completion when acceptance criteria exist but no evidence satisfies them.
2. `completeTask` rejects completion when blockers are still pending or in progress.
3. `completeTask` runs completion hooks before status mutation and keeps the task in progress when a hook blocks.
4. Blocking hook feedback is persisted as a completion attempt and returned as next model input.
5. Closing several implementation tasks without verifier evidence creates a verifier requirement or blocks final reporting.
6. Task selection ignores owned tasks and pending tasks with incomplete blockers; completed blockers are not shown as active blockers.
7. Plan exit is rejected outside plan mode and rejected when the plan artifact lacks `Acceptance` or `Verification`.
8. Plan rejection keeps plan mode active and passes rejection feedback into the next planning turn.
9. Tool evidence records include command/tool name, exit status, output preview, timestamps, and task id.
10. Empty tool output is represented explicitly; large output is persisted with preview plus artifact path.
11. Verifier PASS is rejected if any check lacks exact command/tool and observed output.
12. Verifier role cannot use edit/write tools against project files; temp-script exceptions are scoped and recorded.
13. Final reporting cannot say "tests passed" unless successful evidence records exist for those tests.
14. Permission policy evaluates deny/ask/sensitive checks before allow and returns a stable reason.
15. Headless permission asks deny when hooks/classifier cannot decide.
16. Permission resolve-once behavior handles simultaneous user/classifier/hook answers without double mutation.
17. Unsafe or parse-failed tool calls serialize; read-only/concurrency-safe calls can batch.
18. File edit/write fails when the target changed after the lane last read it.
19. Shell safety, if mew has shell execution: compound `cd` plus write/git requires approval, process substitution/expansion asks, and redirections are validated on the original command.
20. Final done gate downgrades to partial/blocked when verifier verdict is `PARTIAL` or `FAIL`, even if tasks were marked completed earlier.
