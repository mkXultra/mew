# Executive Summary

- Codex stabilizes edit generation by making patch text a first-class, machine-checked artifact: prompt contract -> grammar -> parser -> semantic verifier -> apply path. It does not treat "draft the edit" as an unstructured model step.
- The biggest gap in mew is that `src/mew/work_loop.py` already detects `edit_ready` cached windows and even switches to a focused fast path, but the next turn still has to invent a full dry-run write batch. That leaves both failure buckets alive: exact windows exist but no safe patch appears, or drafting times out.
- Codex review is also isolated and contractual: `core/review_prompt.md` defines a strict reviewer schema, `core/src/tasks/review.rs` runs review in a separate task with restricted capabilities, and `core/tests/suite/review.rs` freezes the lifecycle and prompt/input shape.
- The highest-value adoption for mew is not "more prompting." It is a first-class `patch_draft -> validate -> review -> apply` pipeline that reuses exact cached windows and returns either a reviewer-visible dry-run diff or one exact blocker without falling back into exploratory turns.

# Relevant reference files

- `references/fresh-cli/codex/codex-rs/tools/src/tool_apply_patch.lark`, `references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs`, `references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool_tests.rs`: canonical patch grammar plus frozen tool contract. This is the model/runtime handshake.
- `references/fresh-cli/codex/codex-rs/apply-patch/apply_patch_tool_instructions.md`, `references/fresh-cli/codex/codex-rs/protocol/src/prompts/base_instructions/default.md`: model-facing safety rules repeated in prompt space, not left implicit.
- `references/fresh-cli/codex/codex-rs/apply-patch/src/parser.rs`: syntactic parse boundary and concrete error taxonomy for invalid hunks.
- `references/fresh-cli/codex/codex-rs/apply-patch/src/invocation.rs`: semantic verification layer. It rejects implicit/raw patch bodies, resolves cwd/workdir, ignores unsafe shell shapes, and derives verified file changes before apply.
- `references/fresh-cli/codex/codex-rs/apply-patch/src/lib.rs`: deterministic patch application and unified-diff derivation against live file contents.
- `references/fresh-cli/codex/codex-rs/apply-patch/tests/suite/tool.rs`, `references/fresh-cli/codex/codex-rs/apply-patch/tests/suite/scenarios.rs`, `references/fresh-cli/codex/codex-rs/apply-patch/tests/fixtures/scenarios/README.md`: portable replay harness and negative cases, not just happy-path tool tests.
- `references/fresh-cli/codex/codex-rs/git-utils/src/apply.rs`: structured dry-run preflight pattern via `git apply --check`.
- `references/fresh-cli/codex/codex-rs/core/review_prompt.md`, `references/fresh-cli/codex/codex-rs/core/src/tasks/review.rs`, `references/fresh-cli/codex/codex-rs/core/tests/suite/review.rs`: isolated review prompt, reviewer task wiring, and contract tests for input isolation, lifecycle, and structured output.

# Design Patterns to Adopt Now

- `Patch IR, not just write intents.` Codex gives the model one narrow edit language and then parses it. For mew, add a first-class `patch_draft` or `patch_blocker` artifact between `build_write_ready_work_model_context()` in `src/mew/work_loop.py` and the existing dry-run tools in `src/mew/write_tools.py`. Once `src/mew/work_session.py` marks `plan_item_observations[0].edit_ready`, the next step should be "emit patch IR from cached windows only," not "run the generic next-action planner again."
- `Separate syntax from semantic verification.` Codex parses the patch, then `maybe_parse_apply_patch_verified()` checks it against the live filesystem and computes exact `new_content` and `unified_diff`. This directly addresses mew bucket 1. Today mew has exact-window reuse and dry-run write tools, but no deterministic middle layer that can say "the cached text is stale," "this hunk is ambiguous," or "the patch is ready." Add that layer.
- `Fail with exact blocker classes.` Codex emits specific failures such as invalid hunk, missing context, implicit invocation, or unresolved path/cwd mismatch. Mew should return exact blockers like `missing_exact_cached_window_texts`, `stale_cached_window_text`, `ambiguous_old_text_match`, `overlapping_hunks`, `unpaired_source_edit_blocked`, or `no_material_change` instead of drifting back into exploration.
- `One canonical invocation path.` Codex explicitly warns if patching is attempted through the wrong tool surface and rejects raw patch bodies. Mew currently has prompt planning, dry-run write tool calls, reply-file approval, and reviewer logging as separate surfaces. The same proposed change should flow through one canonical artifact so preview, approval, replay, and apply all inspect the same payload.
- `Tiny draft prompt once windows are ready.` Codex keeps patch instructions short and specific. Mew already has `build_work_write_ready_think_prompt()` and a 90-second timeout extension in `src/mew/work_loop.py`, which is the right direction, but it still asks the model for a full next action. Replace that fast path with a smaller contract: emit only `patch_draft` or one exact blocker. This is the cleanest mitigation for bucket 2.
- `Review as a separate contract, not an afterthought.` Codex review is an isolated reviewer task with its own prompt, disabled extra capabilities, strict JSON output, and lifecycle items. Mew should review dry-run diffs in a similarly isolated lane: diff plus exact cached windows plus verifier context in, structured findings or `patch is correct` out. Do not make review depend on the whole exploratory transcript.
- `Prompt/runtime lockstep tests.` Codex freezes both the tool spec and the review prompt behavior with tests. Mew should add tests that prove the write-ready fast path prompt, patch schema, and validator stay aligned as code changes.

# Test/replay Harness Ideas for mew

- `Cached-window patch fixtures.` Create scenario directories with `input/`, `cached_windows.json`, `plan_item.json`, and `expected.diff` or `expected_blocker.json`. Replay the draft compiler without a live model. This mirrors Codex's portable `apply-patch` scenarios.
- `Validator negative cases.` Add deterministic tests around `src/mew/write_tools.py` or a new patch-draft module for stale old text, duplicated match text, overlapping hunks, truncated cached windows, empty update hunks, and no-op edits. The expected outcome should be an exact blocker string, not a generic failure.
- `Write-ready timeout replays.` Persist the minimal focused context already surfaced by `build_write_ready_work_model_context()` plus `prompt_chars`, `timeout_seconds`, and `write_ready_fast_path_reason`. Re-run the draft step offline against both the current prompt and a patch-only prompt to measure whether the timeout disappears.
- `Review contract tests.` Copy the Codex pattern from `core/tests/suite/review.rs`: ensure reviewer input excludes parent history, reviewer output must match schema, and no streaming chatter leaks into the visible review surface.
- `Approval/apply round-trip fixtures.` Replay `dry_run -> reviewer approval -> apply -> verify -> reviewer_diffs log` and assert that the reviewer-visible draft diff and the applied diff either match or produce an explicit divergence record. This matters because mew already logs reviewer diffs in `src/mew/commands.py`, but the logging is narrower than the actual write surface.

# What not to copy

- `Do not copy Codex's compatibility baggage.` `codex-rs/apply-patch/src/parser.rs` and `.../invocation.rs` carry lenient heredoc parsing, shell extraction, and `applypatch` alias support for model quirks. Mew can stay strict and keep one schema.
- `Do not copy non-transactional multi-file apply semantics.` `references/fresh-cli/codex/codex-rs/apply-patch/tests/suite/tool.rs` explicitly accepts partial success. For mew's reviewer-gated loop, that is the wrong default. Keep dry-run preview first, keep rollback-capable apply paths, and make partial apply exceptional and visible.
- `Do not replace mew's existing write tools with a raw patch CLI.` Mew already has useful deterministic primitives in `src/mew/write_tools.py` and reviewer approval flow in `src/mew/commands.py`. Copy the IR/validator/replay architecture, not the exact Codex surface.

# Proposed next tasks for mew

- `1. Add a patch-draft artifact.` In `src/mew/work_loop.py` and `src/mew/work_session.py`, promote the current `edit_ready` state into a dedicated `patch_draft_ready` lane that asks only for patch IR or an exact blocker.
- `2. Add a deterministic patch validator.` In `src/mew/write_tools.py` or a new `src/mew/patch_draft.py`, validate cached-window-based edits before approval: exact old text, unique placement, disjoint hunks, unified diff generation, and blocker taxonomy.
- `3. Reuse validator output for reviewer-visible dry runs.` Feed the validated diff directly into the existing approval/reply-file surfaces in `src/mew/commands.py` instead of waiting for a second model turn to restate the same change.
- `4. Add replay fixtures before more prompt tuning.` Put the first effort into scenario tests and timeout replays, not another round of prompt wording in `build_work_write_ready_think_prompt()`.
- `5. Add an isolated patch review step.` After draft validation succeeds, review only the diff and exact cached windows with a strict JSON schema. Keep it out of the exploratory main loop.
