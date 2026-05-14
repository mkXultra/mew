# Codex vs Claude Code: Exploration to Patch on `terminal-bench/make-mips-interpreter`

Date: 2026-05-15

Scope note: this review compares only the saved Codex and Claude Code reference traces. mew is intentionally out of scope.

Primary artifacts:

- Codex trace: `proof-artifacts/terminal-bench/reference-trace/codex-make-mips-interpreter-20260507-174138/2026-05-07__17-41-39/make-mips-interpreter__y58SFkq`
- Claude Code trace: `proof-artifacts/terminal-bench/reference-trace/claude-code-make-mips-interpreter-20260507-174138/2026-05-07__17-41-39/make-mips-interpreter__WuLGVMp`

## Executive Summary

Artifact-backed facts:

- Codex reached its first file mutation at 367.803s and final response at 416.420s, with `edit_count: 4` and `command_count: 30` in `normalized-trace/summary.json`.
- Claude Code had no normalized edit before the run ended. Its trace has `edit_count: 0`, last normalized event at 1597.713s, and `result.json` records `AgentTimeoutError: Agent execution timed out after 1800.0 seconds`.
- Codex did not simply "explore less." It made more direct command calls, but it compressed exploration into parallel, implementation-shaped probes: source/file layout, ELF/load segments, symbol/map lookup, disassembly slices, syscall surface, frame output path, opcode/FPU census, and hook candidates.
- Claude Code explored in two layers: an initial blocking `Explore` subagent returned a broad report, then the main agent re-read and re-derived many of the same facts before entering long private design passes. Those design passes consumed large completion budgets and did not produce a file write.
- The strongest concrete difference was step shape: Codex stayed in one synthesis loop and translated each probe into patch constraints; Claude Code inserted a read-only exploration handoff, then repeated verification and attempted to mentally complete the emulator before mutating.

Speculative hypothesis:

- Model/runtime differences may have mattered, but the artifact does not isolate model quality from tool/prompt behavior. The observed delay is explainable without assuming Claude Code was less capable: the trace shows duplicated exploration and long implementation planning after enough patch evidence was already available.

## Timeline Table: Codex vs Claude Code

| Time | Codex | Claude Code |
| --- | --- | --- |
| 0s | Receives task plus `/app` context. | Receives same task. |
| 3-12s | At 7.5s starts direct shell exploration in parallel: file list, source grep, `file/readelf`. | At 3s states analysis plan. At 11.5s launches `Agent` with `subagent_type: Explore` for broad read-only exploration. |
| ~15-43s | Runs `readelf`, map reads, symbol greps, source reads, disassembly and focused disassembly slices. | Main thread waits for Explore result. The normalized trace records the Agent call start at 11.459s; the main thread does not act on its report until about 132s. |
| ~59s | States key implementation constraints: MIPSEL/o32, 1 GB static heap, sparse memory, and `DG_DrawFrame` writes `/tmp/frame.bmp`. | Explore report has already gathered many of these facts, but the main thread has not patched. |
| ~63-125s | Runs opcode/FPU/gp/libc-hook scans. At 123s says it will implement `vm.js`; at 124.8s runs one final MIPS32R2 instruction scan. | From 132s to 283s, repeats direct checks: `ls`, `readelf`, repeated `Read` calls on `my_stdlib.c`, `doomgeneric_img.c`, headers, grep for syscalls, custom Python ELF parsing. |
| 367.8s | First mutation: `apply_patch` adds `/app/vm.js`. | No mutation. By ~283s it has enough direct facts to start a patch, but continues reasoning. |
| 370-382s | Runs `node vm.js`, hits one missing instruction, patches `wsbh`. | At 714s emits a 31,999-token reasoning block with `stop_reason: max_tokens`; it is designing the emulator, not writing it. |
| 404-416s | Verifies BMP files and header, returns final answer. | Later checks `_gp`, entry instructions, LWL/LWR/SWL/SWR and FPU/syscall counts, then emits another 32,000-token reasoning block about unaligned loads. No `Write`/`Edit`; Harbor times out at 1800s. |

## Exploration Pattern Comparison

Artifact-backed facts:

- Codex used direct shell commands from the main context. Several early groups were concurrent in one model turn: for example, at ~7.5s it launched file listing, source grep, and ELF inspection; at ~14-15s it launched multiple `readelf` and map reads; at ~42s it launched several disassembly and symbol checks.
- Codex's exploration was shaped around patch decisions:
  - Memory model: use sparse pages because the ELF has a huge BSS/static heap.
  - ABI/syscalls: custom syscall numbers from `my_stdlib.c`, not normal Linux MIPS syscall offsets.
  - Output target: `/tmp/frame.bmp` from `DG_DrawFrame`.
  - Runtime feasibility: native hooks for expensive libc-like functions while still interpreting guest code.
  - Instruction coverage: targeted census for FPU, unaligned loads/stores, MIPS32R2 bit operations.
- Claude Code's `Explore` agent produced a useful broad report: ELF properties, segments, 1 GB BSS, DoomGeneric interface, frame path, key symbols, and syscall convention.
- The main Claude Code agent then repeated much of that exploration. It re-read source files, reran ELF parsing, rechecked syscall numbers, rechecked `USE_FS`, and wrote custom Python snippets to parse the same ELF header/program-header facts.
- Claude Code also spent long spans in private reasoning after it had the needed facts. Two visible examples in `agent/trajectory.json`:
  - step 37: 28,649 reasoning chars / 31,999 completion tokens, `stop_reason: max_tokens`, no tool call or edit.
  - step 45: 26,471 reasoning chars / 32,000 completion tokens, `stop_reason: max_tokens`, still no edit.

Conclusion:

- Codex explored differently and compressed exploration better. It explored enough to define a runnable skeleton and then let runtime feedback find the remaining gaps.
- Claude Code explored broadly, then re-explored and over-designed. Its exploration was not just longer in wall-clock time; it repeatedly failed to cross the mutation threshold.

## First-Patch Readiness Analysis

A MIPS interpreter patch needed at least these facts:

- ELF class, endianness, entry point, and load segments.
- A memory strategy for the huge data/BSS range.
- The syscall convention and syscall numbers.
- A frame-output success condition.
- Enough instruction-surface knowledge to build an initial interpreter and iterate.

Artifact-backed Codex readiness:

- By ~59s, Codex had committed to sparse memory and identified `/tmp/frame.bmp`.
- By ~104.8s, it had identified libc-like hook candidates.
- At ~123s, Codex explicitly crossed into implementation: "I’m going to implement the CPU core and sparse memory in `vm.js`..."
- At ~124.8s, it ran one final scan for MIPS32R2/unusual instructions, then generated the patch. The 243s between that scan and the first patch was code construction, not additional exploration.

Artifact-backed Claude Code readiness:

- The Explore report already contained most patch prerequisites before the main thread resumed direct work.
- Conservatively, Claude Code had enough evidence by ~283s: it had direct source reads, ELF segment parses, endianness confirmation, syscall checks, `USE_FS` checks, and program-header parsing.
- By ~874-876s, it also had `_gp` and entry-instruction checks, but those were not necessary to begin a first runnable `vm.js` skeleton; they could have been handled by execution feedback.

Speculative hypothesis:

- Claude Code appears to have treated patch readiness as "I can mentally specify a near-complete emulator" rather than "I can build a plausible skeleton and iterate under `node vm.js`." That threshold is too high for this task because emulator correctness is naturally test-driven by missing instruction/runtime failures.

## Source/Tool Architecture Observations

### Codex Reference Source

Artifact-backed source observations:

- Codex's default prompt tells the agent to keep going until the query is resolved and to autonomously resolve the task before returning (`references/fresh-cli/codex/codex-rs/protocol/src/prompts/base_instructions/default.md:123`).
- The same prompt explicitly names `apply_patch` as the file-editing path (`references/fresh-cli/codex/codex-rs/protocol/src/prompts/base_instructions/default.md:132`).
- Codex exposes `parallel_tool_calls` to the model when the model supports it (`references/fresh-cli/codex/codex-rs/core/src/session/turn.rs:941`).
- Its tool registry marks shell / `exec_command` tools as parallel-capable, while `apply_patch` is not parallel-capable (`references/fresh-cli/codex/codex-rs/tools/src/tool_registry_plan.rs:156`, `references/fresh-cli/codex/codex-rs/tools/src/tool_registry_plan.rs:322`).
- Runtime dispatch uses a read/write lock: tools marked parallel acquire a shared read lock; non-parallel tools acquire an exclusive write lock (`references/fresh-cli/codex/codex-rs/core/src/tools/parallel.rs:89`, `references/fresh-cli/codex/codex-rs/core/src/tools/parallel.rs:116`).
- Codex has a dedicated freeform `apply_patch` tool with grammar-level structure, making a large file add a direct first-class mutation operation (`references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs:87`).
- `exec_command` supports explicit `yield_time_ms`, `max_output_tokens`, `workdir`, process IDs, and stdin continuation, which supports fast probe-run-fix loops (`references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs:45`, `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs:222`).

Likely contribution:

- Codex's tool architecture favors main-thread, high-throughput probing followed by direct patching. The trace matches that architecture: lots of early parallel shell probes, one large `apply_patch`, then immediate `node vm.js` feedback.

### Claude Code Reference Source

Artifact-backed source observations:

- Claude Code's system prompt also encourages parallel tool calls when independent (`references/fresh-cli/claude-code/src/constants/prompts.ts:310`).
- Its prompt says subagents are useful for parallelizing independent queries and protecting main context, but also warns against duplicating work already delegated (`references/fresh-cli/claude-code/src/constants/prompts.ts:316`).
- The same prompt explicitly says simple directed searches should use direct search tools, and Explore is slower than direct search; use it only when simple search is insufficient or the task clearly needs more than three queries (`references/fresh-cli/claude-code/src/constants/prompts.ts:378`).
- The `Explore` agent is explicitly read-only and prohibited from creating, editing, deleting, moving, copying, or changing system state (`references/fresh-cli/claude-code/src/tools/AgentTool/built-in/exploreAgent.ts:24`).
- The `Explore` agent is optimized for search/read/report, not mutation (`references/fresh-cli/claude-code/src/tools/AgentTool/built-in/exploreAgent.ts:38`).
- AgentTool usage notes say the agent result is not visible to the user and must be summarized by the parent; they also say outputs should generally be trusted (`references/fresh-cli/claude-code/src/tools/AgentTool/prompt.ts:255`, `references/fresh-cli/claude-code/src/tools/AgentTool/prompt.ts:268`).
- Regular subagents start from initial prompt messages and their own agent system prompt; regular subagents do not simply continue the parent's synthesis state (`references/fresh-cli/claude-code/src/tools/AgentTool/runAgent.ts:368`, `references/fresh-cli/claude-code/src/tools/AgentTool/runAgent.ts:500`).
- Subagent context is intentionally isolated by default to avoid parent-state mutation (`references/fresh-cli/claude-code/src/utils/forkedAgent.ts:307`).
- Explore/Plan omit some parent context such as Claude.md and stale git status to reduce token load; the parent is expected to interpret their output (`references/fresh-cli/claude-code/src/tools/AgentTool/runAgent.ts:385`, `references/fresh-cli/claude-code/src/tools/AgentTool/runAgent.ts:400`).

Likely contribution:

- Claude Code's architecture can be excellent when the parent truly uses subagent output as a trusted compressed result. In this trace, the parent did not do that. The blocking Explore call added a handoff, then the parent duplicated work and kept designing. The architecture did not force the delay, but it made this failure mode available.

## Did The Explore-Agent Pattern Delay Implementation?

Artifact-backed facts:

- The first Claude Code action was a blocking `Explore` agent. The parent did no direct commands until ~132s.
- The Explore report was broad and mostly sufficient for initial patch planning.
- After the Explore result, the parent repeated source and ELF checks for another ~150s before even reaching its own complete syscall/memory summary.
- Even after those direct checks, the parent spent several long private reasoning spans and never wrote `vm.js`.

Answer:

- Yes, the Explore-agent pattern delayed implementation in this trace, but the delay was not only the subagent's wall-clock cost. The larger delay came from ineffective assimilation: the main agent did not trust and compress the Explore report into a patch plan quickly.
- The read-only nature of Explore also matters. It could identify facts, but it could not create a starter interpreter. The parent still had to perform the implementation transition. That transition failed.

Speculative hypothesis:

- The parent may have treated the Explore report as "background research" rather than as a patch-readiness packet. A stronger handoff contract would have asked Explore to return a minimal patch checklist: exact constants, syscalls, symbols, frame path, and first skeleton risks. That could have reduced re-reading.

## General Lessons

Artifact-backed lessons:

- Prefer direct, batched exploration for the critical path when the next action depends on the result. Codex's first 125s were almost all targeted probes that fed directly into implementation.
- Subagents should reduce parent context load, not postpone parent synthesis. If a subagent is used, the parent should explicitly decide what facts are accepted and what minimal extra probes remain.
- Define a first-patch readiness threshold. For emulator tasks, readiness is not full ISA certainty; it is enough evidence to build a skeleton and let execution expose missing instructions/syscalls.
- Convert discoveries into implementation constraints immediately: memory strategy, ABI, output target, hot functions, verification command.
- Use runtime feedback early. Codex's first run quickly exposed a missing `wsbh` case; that is a useful failure, not something that had to be proven away before writing code.
- Avoid long private design passes after the readiness threshold. Claude Code's largest delays were not shell calls; they were reasoning blocks that did not mutate or verify.

Non-lessons:

- Do not conclude "less exploration is better." Codex made many probes; the advantage was compression and direction.
- Do not conclude "never use Explore/subagents." The Explore report was useful. The failure was using it as a blocking first step and then duplicating it.
- Do not conclude this is purely a model-ranking result. The compared runs used different CLIs, prompts, tools, model labels, and runtime structures.
- Do not generalize from the verifier reward; both saved runs have `reward: 0.0`, so this review is only about exploration-to-patch dynamics, not benchmark success.

## Bottom Line

Codex moved faster because its early exploration stayed on the implementation critical path: parallel shell probes, immediate synthesis into constraints, direct `apply_patch`, and quick runtime iteration. Claude Code gathered enough information, but its Explore-agent handoff plus repeated parent-side validation and long internal design loops delayed and ultimately prevented the first mutation.
