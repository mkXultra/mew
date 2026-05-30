# Review 2026-05-14 - M6.24 Codex Tool IF Gap

Scope: compare mew `implement_v2` native tools with the Codex CLI tool interface under `references/fresh-cli/codex`, then decide whether mew should move toward Codex-compatible tool descriptions and interfaces.

## Recommendation

Adopt a **Codex-like hot-path subset**, not full Codex CLI compatibility and not the current mew-specific provider-visible surface.

The best target is:

```text
provider-visible hot path:
  apply_patch, exec_command, write_stdin, optional list_dir/read aliases
  + Codex-shaped terminal output strings
  + ordinary Responses call_id/output pairing

mew-only substrate:
  transcript artifacts, proof manifests, evidence refs, execution contracts,
  source observers, finish gates, replay, forbidden-leak scans
```

Full Codex compliance is not a realistic or desirable goal because Codex's tool surface is config-dependent and tied to its CLI approval, event, sandbox, MCP, and UI systems. But mew should stop teaching the model a different coding interface where common actions are named `run_command`, `run_tests`, `poll_command`, `read_command_output`, `inspect_dir`, `search_text`, and `glob` unless those names are intentionally hidden behind compatibility aliases.

## 1. Codex Actual Coding Tool Shape

Codex exposes tools through a per-turn tool registry. `build_prompt` passes `router.model_visible_specs()` and `parallel_tool_calls` into the request, so the model sees only the enabled registry profile for that turn (`references/fresh-cli/codex/codex-rs/core/src/session/turn.rs:935`). The Responses request carries `model`, `instructions`, `input`, `tools`, `tool_choice: "auto"`, `parallel_tool_calls`, `reasoning`, `store`, `stream`, `include`, `prompt_cache_key`, and optional text controls (`references/fresh-cli/codex/codex-rs/codex-api/src/common.rs:165`, `references/fresh-cli/codex/codex-rs/core/src/client.rs:881`).

Important coding tools:

- `apply_patch`: custom/freeform tool named `apply_patch` with the exact short description "Use the `apply_patch` tool to edit files. This is a FREEFORM tool, so do not wrap the patch in JSON." and a Lark grammar (`references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs:89`). The JSON fallback is also named `apply_patch`, strict false, with one required `input` string (`references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs:101`).
- Shell family is config-dependent. `Default` exposes `shell`, `Local` exposes Responses built-in `local_shell`, `UnifiedExec` exposes `exec_command` and `write_stdin`, and `ShellCommand` exposes `shell_command` (`references/fresh-cli/codex/codex-rs/tools/src/tool_registry_plan.rs:138`, `references/fresh-cli/codex/codex-rs/tools/src/tool_registry_plan.rs:168`).
- `exec_command`: name `exec_command`, strict false, required `cmd`, optional `workdir`, `shell`, `tty`, `yield_time_ms`, `max_output_tokens`, optional `login`, plus approval fields when enabled. Description: "Runs a command in a PTY, returning output or a session ID for ongoing interaction." (`references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs:19`).
- `write_stdin`: name `write_stdin`, strict false, required `session_id`, optional `chars`, `yield_time_ms`, `max_output_tokens`; description says it writes to an existing unified exec session and returns recent output (`references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs:92`).
- `shell`: name `shell`, strict false, required `command: string[]`, optional `workdir`, `timeout_ms`, approval fields. The description tells the model to use `["bash", "-lc"]` and always set `workdir` (`references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs:136`).
- `shell_command`: name `shell_command`, strict false, required command string, optional `workdir`, `timeout_ms`, `login`, approval fields (`references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs:199`).
- `list_dir`: optional experimental tool named `list_dir`, strict false, required absolute `dir_path`, optional `offset`, `limit`, and `depth` (`references/fresh-cli/codex/codex-rs/tools/src/utility_tool.rs:6`).

Codex function and custom calls are ordinary Responses items: `function_call` has `name`, raw JSON `arguments`, and `call_id`; `custom_tool_call` has `name`, `input`, and `call_id`; outputs pair back with `function_call_output` or `custom_tool_call_output` by `call_id` (`references/fresh-cli/codex/codex-rs/protocol/src/models.rs:725`, `references/fresh-cli/codex/codex-rs/protocol/src/models.rs:756`, `references/fresh-cli/codex/codex-rs/protocol/src/models.rs:762`). Output bodies serialize as either a plain string or structured content items; `success` is internal (`references/fresh-cli/codex/codex-rs/protocol/src/models.rs:1316`).

For coding flow, the result shape is more important than formal output schemas. `ResponsesApiTool.output_schema` is skipped during serialization (`references/fresh-cli/codex/codex-rs/tools/src/responses_api.rs:25`). Unified exec returns terminal-shaped text with `Chunk ID`, `Wall time`, `Process exited with code` or `Process running with session ID`, optional original token count, and `Output:` (`references/fresh-cli/codex/codex-rs/core/src/tools/context.rs:453`). When freeform `apply_patch` is present, Codex reserializes shell outputs from JSON into text containing `Exit code`, `Wall time`, optional total lines, and `Output:` (`references/fresh-cli/codex/codex-rs/core/src/client_common.rs:69`, `references/fresh-cli/codex/codex-rs/core/src/client_common.rs:144`).

Codex's agent-facing guidance is mostly base-prompt guidance, not verbose tool descriptions. It tells the model to prefer `rg`, use `apply_patch` for edits where suitable, preserve dirty worktrees, and avoid destructive commands (`references/fresh-cli/codex/codex-rs/core/gpt_5_codex_prompt.md:1`).

## 2. Mew Current `implement_v2` Surface

Mew's provider-neutral base tool order is mutation first, then execution, process lifecycle, read/context, git, and `finish`: `apply_patch`, `edit_file`, `write_file`, `run_command`, `run_tests`, `poll_command`, `cancel_command`, `read_command_output`, `read_file`, `search_text`, `glob`, `inspect_dir`, `git_status`, `git_diff`, `finish` (`src/mew/implement_lane/tool_policy.py:43`). Tests freeze that ordering and the current description style (`tests/test_native_tool_schema.py:54`, `tests/test_tool_policy.py:12`).

Mew lowers `apply_patch` to a Responses custom/freeform tool with a Lark grammar when supported (`src/mew/implement_lane/native_tool_schema.py:127`). The description is currently mew-specific: "Primary source mutation tool..." plus "smallest runnable candidate" and "Do not wrap custom/freeform patch input in JSON" (`src/mew/implement_lane/tool_policy.py:44`). JSON fallback accepts `input`, `patch`, `patch_lines`, and `dry_run`, but only `input` is required (`src/mew/implement_lane/native_tool_schema.py:422`).

Most other mew tools are strict function tools. The lowering path emits `{type:"function", name, description, parameters, strict}` (`src/mew/implement_lane/native_tool_schema.py:377`), and the schema validator enforces all declared fields as required and `additionalProperties: false` (`src/mew/implement_lane/native_tool_schema.py:189`). Command tools expose `command`, `argv`, `cwd`, `timeout_ms`, `max_output_chars`, and `max_output_tokens` (`src/mew/implement_lane/native_tool_schema.py:401`).

The live Responses request is already Codex-like at the transport layer: `model`, `instructions`, `input`, `tools`, `tool_choice: "auto"`, `parallel_tool_calls`, `stream: true`, and `store: false` (`src/mew/implement_lane/native_provider_adapter.py:152`). Tool outputs are paired Responses output items using the same `call_id`; mew builds plain string `function_call_output` and `custom_tool_call_output` items (`src/mew/implement_lane/native_provider_adapter.py:419`). The native transcript validates one-call-one-output pairing, monotonic sequence, call/output kind matching, and tool-name matching (`src/mew/implement_lane/native_transcript.py:210`).

Provider-visible tool output is not the full internal envelope. The harness converts each `ToolResultEnvelope` to `result.natural_result_text()` before appending the output item (`src/mew/implement_lane/native_tool_harness.py:1517`). Internally, the envelope still carries content, refs, side effects, route decisions, and evidence (`src/mew/implement_lane/types.py:165`), and the natural text is rendered from a bounded factual card (`src/mew/implement_lane/types.py:193`, `src/mew/implement_lane/types.py:242`).

Mew has important resident sidecars. The native transcript lists authoritative files such as `response_transcript.json` and `response_items.jsonl`, plus derived proof, evidence, request, and pairing artifacts (`src/mew/implement_lane/native_transcript.py:51`). Sidecar projections are derived from transcript items and evidence refs (`src/mew/implement_lane/native_sidecar_projection.py:1`). The provider-visible leak policy explicitly forbids `required_next`, `first_write_due`, WorkFrame, frontier, proof, todo, and related control fields (`src/mew/implement_lane/affordance_visibility.py:17`).

## 3. Divergences That Likely Hurt Step Flow

1. **Tool names do not match the Codex-conditioned path.** Codex-trained coding behavior expects `apply_patch` plus a shell family, especially `exec_command`/`write_stdin` in unified exec mode. Mew instead exposes `run_command`, `run_tests`, `poll_command`, `cancel_command`, `read_command_output`, `read_file`, `search_text`, `glob`, and `inspect_dir` (`src/mew/implement_lane/tool_policy.py:80`). That gives the model a different action grammar and makes read/probe tools unusually salient.

2. **Mew uses strict nullable schemas where Codex uses optional non-strict schemas.** Codex shell, exec, apply_patch fallback, and list_dir tools are strict false (`references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs:81`, `references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs:110`, `references/fresh-cli/codex/codex-rs/tools/src/utility_tool.rs:30`). Mew strict schemas require every property, often as nullable (`src/mew/implement_lane/native_tool_schema.py:189`). That is provider-valid, but it is not Codex-compatible and can bias calls toward over-specified argument objects.

3. **Several mew schemas do not match runtime arguments.** `inspect_dir` schema says `max_entries`, runtime reads `limit`; `search_text` and `glob` schemas say `max_results`, runtime reads `max_matches`; `git_status` and `git_diff` schemas say `path`/`cached`/`stat`, runtime reads `cwd`/`staged`/`base`; `read_file` runtime supports `line_start` and `line_count` not in the schema; `poll_command` runtime supports `wait_seconds` not in the schema; `read_command_output` runtime supports `tail` but schema omits it (`src/mew/implement_lane/native_tool_schema.py:241`, `src/mew/implement_lane/read_runtime.py:102`, `src/mew/implement_lane/read_runtime.py:121`, `src/mew/implement_lane/read_runtime.py:148`, `src/mew/implement_lane/read_runtime.py:161`, `src/mew/implement_lane/exec_runtime.py:477`, `src/mew/implement_lane/exec_runtime.py:510`). This is a correctness gap independent of Codex compatibility.

4. **Command lifecycle is mew-specific.** Codex unified exec returns a `session_id` and uses `write_stdin` to poll or interact (`references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs:45`). Mew starts a managed command, returns `command_run_id`, and separately exposes `poll_command`, `cancel_command`, and `read_command_output` (`src/mew/implement_lane/exec_runtime.py:322`, `src/mew/implement_lane/exec_runtime.py:477`). This is internally powerful, but it is a different model-facing loop.

5. **Tool output is card-like instead of terminal-like.** Mew returns bounded natural card text with refs, paths, status, failure class, and output tails (`src/mew/implement_lane/types.py:193`). Codex returns terminal-shaped text that makes the latest failure visually immediate (`references/fresh-cli/codex/codex-rs/core/src/tools/context.rs:453`). The mew output is more observable, but it may make the next edit feel like evidence bookkeeping instead of "patch from this failure."

6. **`run_tests` and execution contracts add semantic self-labeling.** Mew intentionally hides `command_intent` and `execution_contract` from schemas (`tests/test_native_tool_schema.py:101`), but runtime still classifies verifier-like commands and uses execution contracts internally (`src/mew/implement_lane/exec_runtime.py:366`, `src/mew/implement_lane/native_tool_harness.py:1500`). The provider-visible `run_tests` tool still creates a conceptual split Codex does not need; Codex mostly uses shell commands and prompt context.

7. **Write defaults are partly Codex-like, partly mew-specific.** Freeform custom `apply_patch` is forced to `apply=True` by the harness (`src/mew/implement_lane/native_tool_harness.py:2024`), which is good. But `write_file`, `edit_file`, and JSON/function writes only apply when `apply` is true or `dry_run` is false (`src/mew/implement_lane/write_runtime.py:101`, `src/mew/implement_lane/write_runtime.py:145`, `src/mew/implement_lane/write_runtime.py:434`). That is safer, but not Codex-like, and it can burn a turn if the model emits an edit-shaped call without the commit flag.

## 4. Safe High-Leverage Changes Now

1. Add a provider-visible **Codex compatibility profile** that exposes `apply_patch`, `exec_command`, and `write_stdin` names. Map them to the existing write and managed-exec internals. Keep old mew tool names available only in legacy or diagnostic profiles until traces prove the aliases work.

2. Make freeform `apply_patch` description match Codex exactly, or nearly exactly. Mew can keep richer patch guidance in static instructions or tests, but the tool description should be the familiar short contract (`references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs:89`, `src/mew/implement_lane/tool_policy.py:47`).

3. Make command output text Codex-shaped for the compatibility profile: `Wall time`, `Process exited with code` or `Process running with session ID`, optional token count, then `Output:`. Preserve refs and evidence in sidecars, with at most a terse footer in model-visible text.

4. Fix schema/runtime drift before or with the compatibility profile. This is safe regardless of final naming. Either make schemas match runtime aliases or update runtime to read the schema names consistently.

5. Prefer Codex-like optional, strict-false schemas for compatibility aliases. Keep strict mew schemas if needed for legacy tools, but do not call the profile Codex-compatible while requiring every nullable field.

6. Add `list_dir` as an alias for `inspect_dir` only if needed. Do not prioritize more read tools. The higher-leverage change is making shell/exec and patch feel native.

7. Treat `run_tests` as an internal semantic tag or legacy alias. In the Codex-like profile, verification should normally be an `exec_command` with a concrete command.

## 5. Differences That Should Remain Mew-Specific

Mew should keep resident/passive proof and observability features that Codex CLI does not need to expose as tools:

- authoritative transcript and response item artifacts (`src/mew/implement_lane/native_transcript.py:51`);
- call/output pairing validation and synthetic error outputs (`src/mew/implement_lane/native_transcript.py:210`);
- proof manifests, evidence refs, typed source mutations, source snapshots, and output refs (`src/mew/implement_lane/write_runtime.py:370`);
- managed command spools, output refs, source observers, artifact checks, and execution-contract normalization (`src/mew/implement_lane/exec_runtime.py:380`);
- finish gates and completion resolver evidence checks (`src/mew/implement_lane/native_tool_harness.py:1555`);
- forbidden provider-visible steering scans (`src/mew/implement_lane/affordance_visibility.py:17`);
- compact factual sidecar digest and request inventory as audit/proof surfaces, not live control protocols (`src/mew/implement_lane/native_tool_harness.py:2045`, `src/mew/implement_lane/native_tool_harness.py:2380`).

The existing M6.24 designs already point in this direction: Codex-like live hot path plus mew-specific durable sidecar proof (`docs/DESIGN_2026-05-13_M6_24_CODEX_LIKE_NATIVE_HOT_PATH.md:52`), and no provider-visible WorkFrame, next-action, first-write pressure, or threshold hints (`docs/DESIGN_2026-05-13_M6_24_CODEX_LIKE_AFFORDANCE_COLLAPSE.md:72`).

## 6. Full Compliance Feasibility And Minimal Migration

Full Codex compliance is not realistic as a near-term target. Codex does not have one stable universal coding tool interface: the shell tool varies by config, optional tools are enabled by feature flags, MCP and plugin tools can alter the surface, and approval semantics are tied to the CLI sandbox and UI. Mew also has obligations Codex does not have: resident transcript proof, replayability, sidecar state, passive observation, and stronger artifact evidence.

Minimal migration plan:

**Phase 0 - Define fixtures.** Freeze a "Codex-like profile" fixture with provider-visible descriptors for `apply_patch`, `exec_command`, `write_stdin`, and optional `list_dir`. Add golden descriptor and output-shape tests against the reference contracts above. Also add failing tests for current schema/runtime drift.

**Phase 1 - Compatibility aliases.** Add `exec_command` and `write_stdin` aliases over managed exec. `exec_command.cmd` maps to current command normalization. `workdir`, `yield_time_ms`, and `max_output_tokens` map to existing `cwd`, foreground wait, and output budget. A yielded command returns a Codex-like session id that maps internally to `command_run_id`.

**Phase 2 - Patch and output shape.** Change the compatibility profile's `apply_patch` description to the Codex short description, keep custom grammar, and ensure freeform patch remains directly mutating after normal write approval. Render command outputs in Codex terminal format while preserving rich refs in sidecars.

**Phase 3 - Reduce mew-specific hot-path salience.** Hide `run_command`, `run_tests`, `poll_command`, `cancel_command`, `read_command_output`, `search_text`, `glob`, and `inspect_dir` from the default Codex-like provider-visible profile. Keep them for legacy modes, internal recovery, or explicit non-Codex profiles. If hiding read tools is too risky, first keep only low-salience aliases and compare traces.

**Phase 4 - Trace validation.** Compare first-write latency, edit-verify-repair cadence, number of read/probe calls before first mutation, and successful acceptance evidence across the old profile and the Codex-like profile. Do not add visible controller pressure if the profile still over-probes; adjust tool/output salience first.

## Final Recommendation

Choose **Codex-like subset**.

Do not aim for full Codex CLI compliance. Do not keep the current mew-specific tool interface as the default provider-visible coding surface. Make the hot-path tools and result text familiar to Codex-conditioned models, and keep mew's stronger proof, replay, sidecar, and observer features behind that interface.
