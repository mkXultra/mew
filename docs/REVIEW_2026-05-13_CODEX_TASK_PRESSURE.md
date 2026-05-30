# Codex Task Pressure Review

Date: 2026-05-13

Scope:
- Codex CLI source: `references/fresh-cli/codex`
- Codex reference trace: `proof-artifacts/terminal-bench/reference-trace/codex-make-mips-interpreter-20260507-174138`
- Mew smoke artifact: `proof-artifacts/terminal-bench/harbor-smoke/mew-make-mips-interpreter-step-check-10min-20260513-215502`

## Findings

### 1. Codex does not appear to have explicit task-pressure controls

I found no Codex source-level control that forces transition from exploration to editing based on first-write deadline, probe count, max probes, turn threshold, or forced patch transition.

The closest matches in source are unrelated deadlines for UI, tests, process output collection, provider stream retries, review timeouts, and similar infrastructure. Source search for `first_write`, `probe budget`, `max probe`, `forced patch`, `turn threshold`, and related terms did not find a coding-task pressure policy in `codex-rs`.

Relevant source points:
- `references/fresh-cli/codex/codex-rs/core/src/tasks/regular.rs:71` runs regular tasks by repeatedly calling `run_turn`, and only loops while the session has pending user input.
- `references/fresh-cli/codex/codex-rs/core/src/session/turn.rs:118` documents the model-turn loop: the model emits function calls or an assistant message; tool outputs are sent back on the next sampling request.
- `references/fresh-cli/codex/codex-rs/core/src/session/turn.rs:429` builds the next model prompt from cloned conversation history.
- `references/fresh-cli/codex/codex-rs/core/src/session/turn.rs:458` decides follow-up from `model_needs_follow_up` or pending user input, not from probe/edit counters.
- `references/fresh-cli/codex/codex-rs/core/src/session/turn.rs:1051` has a provider stream retry budget, which is transport recovery, not task pressure.
- `references/fresh-cli/codex/codex-rs/core/src/session/turn.rs:2099` follows up when the API says `end_turn=false`; again, this is not edit pressure.

### 2. Earlier Codex editing is plausibly caused by structure and affordance

The reference trace starts with normal exploration, then edits at step 32:
- Codex launch uses `codex exec --dangerously-bypass-approvals-and-sandbox --model gpt-5.5 --json --enable unified_exec -c model_reasoning_effort=high`: `proof-artifacts/terminal-bench/reference-trace/codex-make-mips-interpreter-20260507-174138/2026-05-07__17-41-39/make-mips-interpreter__y58SFkq/trial.log:8`
- Agent execution ran from `08:42:24Z` to `08:49:26Z`: `proof-artifacts/terminal-bench/reference-trace/codex-make-mips-interpreter-20260507-174138/2026-05-07__17-41-39/make-mips-interpreter__y58SFkq/result.json:97`
- First source edit is `apply_patch` adding `/app/vm.js` at `08:48:37.567Z`, about 368 seconds after the user prompt in the trajectory: `proof-artifacts/terminal-bench/reference-trace/codex-make-mips-interpreter-20260507-174138/2026-05-07__17-41-39/make-mips-interpreter__y58SFkq/agent/trajectory.json:785`
- The trace has 30 `exec_command` calls before/during the run and 2 `apply_patch` calls overall. After the first patch, Codex immediately runs `node vm.js`, observes an unsupported instruction, patches once, and reruns: `proof-artifacts/terminal-bench/reference-trace/codex-make-mips-interpreter-20260507-174138/2026-05-07__17-41-39/make-mips-interpreter__y58SFkq/agent/codex.txt:56`

Plausible mechanisms:
- Base prompt action orientation. Codex tells the model to persist through implementation, assume code changes when the request implies them, and use `apply_patch`: `references/fresh-cli/codex/codex-rs/core/gpt_5_2_prompt.md:29`, `references/fresh-cli/codex/codex-rs/core/gpt_5_2_prompt.md:118`, `references/fresh-cli/codex/codex-rs/models-manager/prompt.md:123`, `references/fresh-cli/codex/codex-rs/models-manager/prompt.md:132`.
- First-class freeform patch tool. Codex exposes `apply_patch` as a custom grammar tool when supported: `references/fresh-cli/codex/codex-rs/tools/src/tool_config.rs:192`, `references/fresh-cli/codex/codex-rs/tools/src/tool_registry_plan.rs:322`, `references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs:87`.
- Text-shaped patch history. When freeform `apply_patch` is present, Codex reserializes shell outputs as text-style history rather than JSON-heavy tool payloads: `references/fresh-cli/codex/codex-rs/core/src/client_common.rs:65`.
- Shell patch normalization. If the model tries to invoke `apply_patch` through shell, Codex intercepts it and warns the model to use the patch tool directly: `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/apply_patch.rs:469`.
- Minimal loop semantics. Codex does not create a separate "probe phase" abstraction for the model. It offers shell plus patch tools, returns outputs, and lets the model choose the next call.
- Approval friction is absent in the reference run because `--dangerously-bypass-approvals-and-sandbox` is used: `proof-artifacts/terminal-bench/reference-trace/codex-make-mips-interpreter-20260507-174138/2026-05-07__17-41-39/make-mips-interpreter__y58SFkq/trial.log:8`.

### 3. Mew's latest artifact shows provider-hidden pressure signals but no write

The mew smoke has the failure shape described in the prompt:
- Launched with `--max-wall-seconds 600 --max-steps 90`, implement_v2 native transcript loop: `proof-artifacts/terminal-bench/harbor-smoke/mew-make-mips-interpreter-step-check-10min-20260513-215502/2026-05-13__21-55-02/make-mips-interpreter__gGVS9Xe/agent/terminal-bench-harbor-smoke/unknown-task/command-transcript.json:2`
- Transcript metrics: 40 calls, 40 outputs, valid pairing, zero writes: `proof-artifacts/terminal-bench/harbor-smoke/mew-make-mips-interpreter-step-check-10min-20260513-215502/2026-05-13__21-55-02/make-mips-interpreter__gGVS9Xe/agent/terminal-bench-harbor-smoke/unknown-task/transcript_metrics.json:2`, `proof-artifacts/terminal-bench/harbor-smoke/mew-make-mips-interpreter-step-check-10min-20260513-215502/2026-05-13__21-55-02/make-mips-interpreter__gGVS9Xe/agent/terminal-bench-harbor-smoke/unknown-task/transcript_metrics.json:22`
- Early calls are read/probe calls: `response_items.jsonl:2`, `response_items.jsonl:5`
- Late calls are still probe commands against `my_stdlib.c`: `response_items.jsonl:98`, `response_items.jsonl:100`
- The run failed from provider read timeout after 24 turns: `mew-report.json:473`, `mew-report.json:484`, `mew-report.json:509`

Mew already computes first-write pressure-like signals, but the artifact records them as diagnostic-only and provider-hidden:
- `first_write_probe_threshold=18`, `first_write_turn_threshold=10000`: `provider-request-inventory.json:19`
- `first_write_due=false` on the first request and related signals are under `diagnostic_loop_signals`: `provider-request-inventory.json:11`
- `provider_visible=false` for diagnostic fields: `provider-request-inventory.json:90`
- forbidden provider-visible steering keys include `first_write_due`, `first_write_probe_threshold`, `first_write_turn_threshold`, and the report says none were visible: `provider-request-inventory.json:110`, `provider-request-inventory.json:127`

Mew also already exposes custom freeform `apply_patch` in the provider request:
- `native-provider-requests.json:551` shows `apply_patch` as a `custom` tool in the live request.
- Source confirms the intended freeform lowering when supported: `src/mew/implement_lane/native_tool_schema.py:127`.

So the gap is not simply "mew lacks apply_patch." The observed gap is that the surrounding prompt/tool ecosystem makes continued probing the dominant path.

### 4. What mew should copy structurally

Copy Codex's structural incentives:
- Keep the provider-visible loop simple: transcript history plus tools, not a rich planner/frontier/probe state machine.
- Keep freeform `apply_patch` first-class and direct. Mew already has this in native schema; protect it from fallback regressions.
- Keep tool results compact but immediately actionable. Codex's command output is model-visible terminal text; mew's evidence refs and summaries should avoid hiding the key next-edit signal behind artifact indirection.
- Make the base prompt shorter and more action-oriented. Codex's strongest pressure is "assume implementation, edit, verify," not numeric budgets.
- Preserve patch-after-failure rhythm: first coherent artifact, run verifier/runtime, then use the latest concrete failure to patch.

### 5. What mew should avoid inventing

Avoid turning this into a hard task-pressure policy:
- Do not add a provider-visible "first write by N turns/seconds" rule as default behavior.
- Do not force a patch after N probes. It risks low-quality edits and task-specific gaming.
- Do not add more verbose probe-budget prose to the prompt. `src/mew/implement_lane/prompt.py:124` already says "cheap probe -> coherent patch/edit -> verifier," but the same section repeatedly names probe/fallback behavior through `src/mew/implement_lane/prompt.py:143`, and the artifact still loops on probes.
- Do not overfit this MIPS task by injecting MIPS-specific edit pressure. The reference Codex behavior looks like general coding-agent affordance plus a coherent initial design, not a terminal-bench-specific transition rule.

## Recommendation

Do not copy an explicit Codex pressure knob; I did not find one.

For mew, keep first-write/probe thresholds as telemetry and diagnostics, not provider-visible steering. The next structural repair should be to make implement_v2 more Codex-like in the provider-visible hot path:

1. Shorten the visible implement_v2 prompt to "inspect enough, create the smallest runnable artifact, run the verifier, repair from the latest failure."
2. Reduce read/probe tool salience where possible. For this class of task, `run_command` plus direct freeform `apply_patch` is closer to Codex than a large read/search/glob/probe vocabulary.
3. Ensure command outputs surface the concrete edit signal directly in transcript text, not only via evidence refs.
4. Keep `apply_patch` custom/freeform as the preferred write path and continue routing shell-invoked patches into it.
5. Measure first-write elapsed/probe count after the run, but do not force the model during the run unless a later experiment proves a generic guard improves outcomes without degrading correctness.

The short version: copy Codex's affordance and transcript shape, not a nonexistent first-write deadline.
