# Codex Hot Path Divergence Beyond Tool Interface

Date: 2026-05-15

## Executive Summary

`codex_hot_path` did align the visible tool surface closely enough to rule out the old "wrong tool names/descriptions" diagnosis as the primary explanation for this run. The candidate exposed `apply_patch`, `exec_command`, `write_stdin`, and `finish`; used provider-native Responses calls; paired every tool call with exactly one output; and used `previous_response_id` after the first request.

The remaining divergence is upstream of mutation transport. Codex received a natural task message in a Codex conversation and, after focused ELF/source probing, created `/app/vm.js` at 367.803s. mew received an implement_v2 JSON-shaped task envelope led by a visible compact sidecar digest plus lane/evidence contracts. It then spent the comparable window reading source and shifted into native Doom recompilation under `/tmp/doom-build` at 284.969s. It never emitted an `apply_patch` call, so apply_patch execution cannot be the proximate failure.

The strongest current explanation is a compound mismatch in provider-visible transcript shape, base instructions, and salience. `previous_response_id` is present, but mew's wire input repeatedly refreshes a model-visible sidecar/task envelope and relies on prior response IDs for most older items. Codex source shows a broader response-item history model, special output formatting when freeform `apply_patch` is active, and default instructions/personality outside mew's implement_v2 lane prompt. Tool IF alignment is necessary, but not sufficient.

## Evidence Table

| Area | Codex behavior | mew `codex_hot_path` behavior | Assessment |
| --- | --- | --- | --- |
| Task presentation | The normalized Codex trace starts with system/developer context, an environment context, then the plain user task: implement `vm.js` for `/app/doomgeneric_mips` and `node vm.js`. See `proof-artifacts/terminal-bench/reference-trace/codex-make-mips-interpreter-20260507-174138/2026-05-07__17-41-39/make-mips-interpreter__y58SFkq/normalized-trace/agent_trace.jsonl`. | The first provider input item is a JSON object beginning with `compact_sidecar_digest`, then `lane`, `task_contract`, `task_facts`, and `workspace`. The natural task text is nested under `task_contract.description`. See `.../candidate-codex-hot-path/.../native-provider-requests.json`, request 1. | The model-visible task is not equivalent even though the semantic task is equivalent. The first salient object in mew is runtime/evidence scaffolding, not the user's imperative. |
| Visible tools | Codex reference used `exec_command`, `write_stdin`, and freeform `apply_patch` in the trace. | Candidate provider tools are exactly `apply_patch`, `exec_command`, `write_stdin`, `finish`; A/B report records `provider_visible_schema_bytes=1839`, `pairing_valid=true`, and no hidden steering markers. | The old broad tool-surface mismatch is not enough to explain this run. |
| First mutation | Codex created `/app/vm.js` with `apply_patch` at 367.803s, then ran `node vm.js`, patched `wsbh`, and verified frame output. `summary.json` reports `first_edit_seconds=367.803`, `command_count=30`, `edit_count=4`. | Candidate never called `apply_patch`. A/B report records `mutation_count=0`, `first_write_turn=null`, `command_count_before_first_write=75`; normalized summary records `source_mutation_count=0`. | The failure happened before mutation transport or patch application. |
| Probe trajectory | Codex probes are focused on ELF layout, symbols, syscall path, frame-writing code, opcode counts, floating point, gp, and a short list of runtime symbols. | mew probes those areas too, but repeatedly rereads source files and then tries native gcc builds in `/tmp/doom-build` at 284.969s, 339.057s, 371.825s, 468.200s, 523.001s, and 585.963s. | The candidate changed the task interpretation from "write interpreter" toward "rebuild/substitute native Doom", despite instructions saying not to rebuild provided artifacts. |
| Instructions | Codex request construction uses `prompt.base_instructions.text` as `instructions` and `prompt.get_formatted_input()` as input (`references/fresh-cli/codex/codex-rs/core/src/client.rs:840-885`). The reference trace includes Codex's larger coding-agent system context. | Candidate instructions are only implement_v2 lane/tool/coding contracts. They say "finish only with fresh tool evidence" and "Make source changes with apply_patch or edit_file", even though `edit_file` is not in the hot-path tool set. | mew did not recreate Codex's hidden/default instruction ecology. The extra evidence/tool-pairing framing likely increases probing salience. |
| Response-item continuity | Codex source treats every non-system item as API history, including reasoning, tool calls, tool outputs, custom calls, shell calls, and compactions (`references/fresh-cli/codex/codex-rs/core/src/context_manager/history.rs:474-490`). The WS path sends `previous_response_id` plus incremental input when available (`client.rs:990-1010`). | mew request 1 has no `previous_response_id`; subsequent requests include it. Wire input length is usually 2 after request 1: one refreshed sidecar/task user item plus latest tool output(s). `reasoning_sidecar_refs_used` is 0 for sampled requests. Source says the delta sends suffix plus `previous_response_id` when the logical transcript prefix matches (`src/mew/implement_lane/native_provider_adapter.py:262-330`). | Use of `previous_response_id` is present, but transcript equivalence is unproven. The visible refresh item changes salience every turn. |
| Reasoning history | Codex includes encrypted reasoning content when reasoning is enabled (`client.rs:856-858`) and stores response items in the session history model. | Candidate requests include `reasoning.encrypted_content`; `response_items.jsonl` has 42 reasoning items, 75 function calls, 75 outputs, but local requests do not replay reasoning items except through provider response continuity. | This may be okay if provider continuity is exact, but it should be audited. It is not equivalent by construction to a full local replay transcript. |
| Tool output rendering | Codex reserializes structured shell output to `Exit code`, `Wall time`, `Output` when freeform `apply_patch` is present (`references/fresh-cli/codex/codex-rs/core/src/client_common.rs:65-79`, `144-166`). | mew renders outputs as `Chunk ID`, `Wall time`, `Process exited/running`, `Original token count`, `Output`, plus stdout/stderr labels. Sidecar digest also carries latest tool result summaries and evidence refs. | Similar but not identical. mew adds runtime identifiers and evidence framing that can compete with task facts. |
| Sidecar/workframe leakage | Not applicable in Codex reference. | Provider inventory shows `compact_sidecar_digest_wire_visible=true`, model-visible sections include `native_transcript_window` and `compact_sidecar_digest`; forbidden WorkFrame/frontier/proof/todo fields are not detected and diagnostic loop signals are reported provider-invisible. | Classic WorkFrame leakage appears controlled, but the visible sidecar itself is intentional scaffolding leakage. |
| Apply patch affordance | Codex freeform tool description is concise and grammar-backed: "Use the `apply_patch` tool to edit files. This is a FREEFORM tool..." (`references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs:89-98`). Codex also intercepts apply_patch-shaped shell commands and warns the model to use the tool (`references/fresh-cli/codex/codex-rs/core/src/tools/handlers/apply_patch.rs:468-565`). | Candidate exposes a custom/freeform `apply_patch` with grammar and a stronger description: "Primary source mutation tool..." Runtime can parse patch text and rejects structured path/edits bypasses (`src/mew/implement_lane/write_runtime.py:1089-1113`). | Patch transport is plausibly close enough for first-order alignment, and it was never exercised. It should not be the next primary fix. |
| Output volume/compaction | Codex final usage in `agent/codex.txt` shows very large cached input volume. It saw enough source/objdump information to synthesize the VM. | Candidate A/B report records only 67,042 provider-visible output bytes over 75 outputs, and many outputs carry `Original token count` with compacted display. | Compaction may make synthesis harder, but the earlier task-framing divergence is stronger evidence. |
| Environment affordances | Codex used `llvm-objdump`; an early `file doomgeneric_mips` probe failed in the reference trace. | mew saw `mips-linux-gnu-objdump`, `gcc`, and `node`, while `file` was absent. The presence of gcc made native-rebuild attempts easy. | Environment affordance likely contributed to the wrong branch, but the prompt already tried to forbid rebuild/substitute behavior and failed to steer it. |

## Ranked Hypotheses

1. **Provider-visible prompt/transcript shape is the dominant divergence. Confidence: high.**

   Evidence: Codex receives a plain user task after environment context. mew's first visible item begins with `compact_sidecar_digest`, then structured lane/task facts. The task text is nested, and every subsequent request refreshes sidecar/task context. This is a major salience change, not just a metadata wrapper.

   Validate with existing-style diagnostics by persisting a normalized "model-visible first 4k chars" snapshot for Codex and mew, then running a controlled replay where the sidecar is hidden or moved after the plain user task. Success criterion: first 20 tool calls move closer to Codex and first mutation targets `vm.js` before native rebuild attempts.

2. **Hidden/default Codex instructions are not reproduced by implement_v2 instructions. Confidence: high.**

   Evidence: Codex source sends `prompt.base_instructions.text` as the provider `instructions`, and the reference trace includes a large coding-agent system context. mew sends only implement_v2 lane/tool/coding contracts. Those contracts emphasize provider-native transcript, paired results, evidence, and finish discipline. The coding contract contains a useful "create missing path early" instruction, but it is buried after the lane/tool protocol and even mentions unavailable `edit_file`.

   Validate by adding an observability comparison of full `instructions` text and section hashes, then running a hot-path variant that uses Codex base instructions plus only a minimal mew safety/finish suffix. Success criterion: reduced probing and earlier `apply_patch` without adding task-specific steering.

3. **`previous_response_id` continuity is present but not proven equivalent. Confidence: medium-high.**

   Evidence: mew uses `previous_response_id` from request 2 onward, but the wire input normally contains a refreshed user sidecar plus latest output(s). Codex source's history manager treats reasoning, tool calls, and outputs as API messages, while mew depends on provider-side continuity and records no local `reasoning_sidecar_refs_used`.

   Validate by adding a continuity audit: for each turn, reconstruct the logical transcript prefix, the wire suffix, previous response id, and response output items; confirm the provider chain contains every function call/output/reasoning item the model needs. Also run a no-delta replay in a sandboxed diagnostic to compare behavior. Do not change continuity behavior until this audit is available.

4. **Raw tool result rendering and sidecar evidence salience make mutation less likely. Confidence: medium.**

   Evidence: Codex's source renderer produces concise `Exit code`, `Wall time`, `Output` text for shell results under freeform apply_patch. mew's renderer includes `Chunk ID`, process/session details, `Original token count`, stdout/stderr subdivisions, and sidecar latest-tool/evidence refs. The A/B report confirms `codex_terminal_text_v1`, but that is not byte-identical to Codex's renderer.

   Validate by rendering identical command results through both renderers and saving side-by-side snapshots. Then run an A/B where only the renderer changes while the sidecar remains fixed, and another where only the sidecar is hidden. This separates output syntax from sidecar salience.

5. **Command output compaction may remove synthesis-critical context. Confidence: medium.**

   Evidence: mew produced 67k provider-visible output bytes over 75 outputs; Codex consumed a much larger cached input stream and wrote a full interpreter after source/ELF probes. mew repeatedly reread source and never consolidated into a design. That is consistent with either missing detail or task-salience failure.

   Validate by recording exact visible length, truncation reason, and omitted-token estimate per tool result. Compare the Codex probe set against mew-rendered equivalents and identify whether key facts for `vm.js` construction are missing.

6. **Apply_patch custom/freeform transport is not the proximate cause, but later parity gaps remain. Confidence: medium.**

   Evidence: Candidate never emitted `apply_patch`. Codex's freeform tool description and grammar are concise; mew also exposes a grammar-backed custom/freeform tool. Codex has extra affordances around shell interception and file-change events, but those matter after the model decides to mutate.

   Validate with a synthetic, existing-artifact-only prompt that requires immediate creation of a trivial file using `apply_patch` under `codex_hot_path`. If the model still avoids `apply_patch`, revisit tool affordance. Otherwise keep focus on prompt/transcript shape.

7. **Sidecar/workframe leakage is controlled for forbidden fields but not for scaffolding salience. Confidence: medium-low.**

   Evidence: Provider inventory says WorkFrame/frontier/proof/todo/next_action fields are absent and diagnostic loop signals are provider-invisible. However, `compact_sidecar_digest` itself is visible and includes runtime id, lane attempt id, provider input authority, hashes, latest tool results, and evidence refs.

   Validate by scanning provider-visible text for non-forbidden scaffolding terms such as `lane_attempt_id`, `provider_input_authority`, `evidence_refs`, `runtime_id`, `sidecar_hashes`, and correlating their presence with long probe loops.

8. **Environment affordances nudged mew toward the wrong solution branch. Confidence: low-medium.**

   Evidence: mew detected `gcc` and `mips-linux-gnu-objdump`; native rebuild attempts then dominated. Codex also had enough tooling to inspect the ELF but did not try to rebuild Doom. This is likely a contributor, not root cause.

   Validate by comparing tool availability snapshots across both artifacts and checking whether a prompt-shape fix prevents native rebuild attempts without changing the environment.

9. **Randomness alone explains the divergence. Confidence: low.**

   Evidence: Same model family, same task, same broad time window, but materially different request shape and instructions. Stochasticity may vary details, but does not explain the systematic native-rebuild branch under an evidence-heavy lane envelope.

   Validate only after prompt/transcript controls are tightened.

## Recommended Next Changes

### Observability-only

1. Save a normalized provider-visible request diff for Codex vs mew: instructions, input item roles/types/order, first 4k chars of model-visible text, tool specs, `previous_response_id`, `store`, `include`, `tool_choice`, and `parallel_tool_calls`.

2. Add an "effective transcript continuity" audit for mew: per turn, record logical input item count, wire input item count, previous response id, prefix match mode, response output item ids, and whether reasoning/tool output items are carried by local replay or provider continuity.

3. Add a prompt-salience snapshot that flags whether the plain user task is the first model-visible content or is preceded by sidecar/runtime JSON.

4. Add renderer parity snapshots: render the same command results through mew `codex_terminal_text_v1` and the Codex source renderer shape (`Exit code`, `Wall time`, `Output`) and persist byte-level diffs.

5. Track task-branch metrics: first target-path creation opportunity, first mutation to a missing path, first non-target rebuild/substitute attempt, and first command that writes outside the requested artifact path.

6. Persist command-output compaction metadata per tool result: visible chars, original token estimate, truncation policy, and whether stdout/stderr was summarized or omitted.

7. Add a scaffolding-salience scan distinct from forbidden WorkFrame leakage. The current forbidden scan is useful, but it does not say whether visible runtime/evidence vocabulary is dominating the prompt.

### Behavior changes

1. Make `codex_hot_path` initial input Codex-like: environment context plus the plain user task as first-class user text. Move `task_contract`, `task_facts`, and sidecar digest out of the leading visible position.

2. Replace the hot-path implement_v2 base prompt with Codex-style base instructions, then append only the smallest required mew constraints for paired outputs, finish reporting, and safety. Avoid lane identity and evidence process language in the main instructions.

3. Hide or shrink `compact_sidecar_digest` for live model input. If it must remain on wire for auditability, prefer opaque hashes or non-leading metadata over narrative JSON with latest tool results and evidence refs.

4. Align command output rendering more exactly with Codex: `Exit code`, `Wall time`, `Output`, with no `Chunk ID`, evidence refs, runtime ids, or token-count prose in model-visible output unless explicitly needed.

5. Keep a normal task-domain guard for this benchmark class: when `task_facts.missing_workspace_paths` contains `vm.js` and the verify command is `node vm.js`, creation or update of that path should be the expected next implementation branch before native rebuild experiments. This should be expressed as task context, not as WorkFrame/next-action machinery.

6. After prompt/transcript/render changes, run the same existing diagnostic harness to compare first 20 calls, first mutation turn, and whether the candidate attempts `/tmp/doom-build` before `vm.js`.

## Do Not Change Yet

1. Do not treat `apply_patch` transport as the primary fix for this failure. The model never attempted `apply_patch`, so patch execution was not reached.

2. Do not disable `previous_response_id` or switch to full local replay as a behavior change until the continuity audit proves a gap. The current evidence shows use of previous response ids, not that they are broken.

3. Do not remove command-output compaction globally. Measure exact lost content first; broad expansion could increase cost and noise without addressing salience.

4. Do not add stronger WorkFrame, next-action, proof, or frontier machinery to the live prompt. The current evidence points toward too much visible process scaffolding, not too little.

5. Do not tune randomness, seed, or model effort as the first response. Provider seed is unsupported in the A/B report, and the observed divergence is structurally explained by request-shape differences.

6. Do not hide `gcc`/`objdump` from the environment as the first-line fix. That could mask the native-rebuild symptom while leaving prompt/transcript divergence unresolved.

7. Do not declare parity from matching provider tool names and descriptions alone. For this benchmark, parity needs at least provider-visible prompt shape, response-item continuity, output rendering, base instructions, and mutation affordance to be compared together.
