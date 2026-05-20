# Design 2026-05-20 - M6.25 Implement V2 Default Native Refactor

Status: reviewed-design candidate for the M6.25 implement lane v2 refactor.
Design only. This document does not authorize runtime/source/test changes by
itself.

Scope: make the selected `implement_v2` path maintainable before more resident
experiments by making the intended native defaults explicit, quarantining
legacy model-JSON behavior, and removing the need to pass hot-path/planner
flags for ordinary runs.

## Decision

The production `implement_v2` default should be:

```text
selected_lane=implement_v2
  -> provider-native Responses loop
  -> default tool surface: codex_hot_path
  -> no provider-visible finish tool
  -> internal done-candidate finish gate
  -> finish verifier planner enabled by default when eligible
  -> proof and observability sidecars preserved
```

`model_json` is not a fallback for production `implement_v2`. If any
model-JSON support remains, it must be explicitly named `legacy_model_json` or
`test_model_json`, excluded from production imports, and accepted only for old
artifact replay or targeted migration tests.

The `mew_legacy` tool surface may remain selectable as a diagnostic opt-out
while the default switch is stabilized, but it should stop being the implicit
default. A caller should not have to pass `tool_surface_profile_id=codex_hot_path`
or `finish_verifier_planner=true` for the standard M6.25 path.

## Current State Observed

The source already has a production native route:

- `src/mew/commands.py` imports and calls `run_live_native_implement_v2` for
  `selected_lane=implement_v2`.
- `src/mew/implement_lane/registry.py` reports
  `runtime_id=implement_v2_native_transcript_loop`,
  `runtime_available=True`, and `provider_native_tool_loop=True` for v2.
- `src/mew/implement_lane/native_tool_harness.py` owns the live native loop,
  native request construction, provider turn execution, done candidates,
  internal finish gate wiring, planner artifacts, and native proof artifacts.
- `src/mew/implement_lane/native_provider_adapter.py` lowers requests to
  provider-native Responses payloads with tools, streaming, `store=false`,
  previous-response delta support, and native response item parsing.
- `src/mew/implement_lane/tool_profiles/codex_hot_path.py` owns the desired
  Codex-like visible tool surface: `apply_patch`, `exec_command`,
  `write_stdin`, plus optional `list_dir`.

The remaining maintainability problem is defaults and quarantine:

- `src/mew/implement_lane/tool_registry.py` still sets
  `DEFAULT_TOOL_SURFACE_PROFILE_ID = MEW_LEGACY_PROFILE_ID`, so missing profile
  config selects `mew_legacy`.
- `src/mew/commands.py` reads `tool_surface_profile_id` from work guidance and
  only writes it into `lane_config` when provided.
- `src/mew/commands.py` sets `experimental_finish_verifier_planner` from
  `finish_verifier_planner` work guidance; missing guidance disables the
  planner.
- `src/mew/implement_lane/native_tool_harness.py` also treats missing
  `experimental_finish_verifier_planner` as disabled inside
  `_native_finish_verifier_planner_can_run()` and
  `_finish_verifier_planner_loop_request()`, so fixing only CLI guidance would
  not make the planner default-enabled.
- `src/mew/mew_harbor_runner.py` defaults to
  `selected_lane=implement_v2 write_integration_observation_detail=true
  finish_verifier_planner=true`, but `--tool-surface-profile-id` is still an
  optional flag and the default guidance does not name `codex_hot_path`.
- Several production paths still import legacy tool-spec resolver functions
  directly from `tool_profiles/mew_legacy.py`: `native_provider_adapter.py`
  and `tool_harness_contract.py` import `list_v2_base_tool_specs`,
  `substrate_inventory.py` imports `list_v2_base_tool_specs` and
  `list_v2_tool_specs_for_mode`, `native_tool_harness.py` imports
  `list_v2_tool_specs_for_task`, and
  `workframe_variant_transcript_tool_nav.py` imports
  `list_v2_base_tool_specs` as a fallback. Other production-facing entry
  points such as `src/mew/commands.py`, `src/mew/tool_kernel.py`, and
  package exports in `src/mew/implement_lane/__init__.py` also expose or call
  `list_v2_*` symbols. A default constant switch alone would leave spec
  resolution tied to the legacy profile outside the active profile registry.
- `src/mew/implement_lane/native_tool_harness.py`,
  `src/mew/implement_lane/tool_lab.py`, and
  `src/mew/implement_lane/hot_path_fastcheck.py` still import helper symbols
  from `v2_runtime.py`, including prompt-history JSON rendering for fastcheck.
  These imports need a production-safe helper split before `v2_runtime.py` can
  become a clearly legacy model-JSON module.
- `src/mew/implement_lane/v2_runtime.py` still contains
  `run_live_json_implement_v2`, the large legacy model-JSON loop, and
  `implement_v2_model_json_tool_loop` artifact identity.
- `src/mew/implement_lane/provider.py` still contains `JsonModelProviderAdapter`
  with provider id `model_json`.
- `src/mew/implement_lane/native_validation.py` already has a static gate that
  rejects production native paths containing legacy model-JSON symbols, but it
  does not yet encode the new default-profile or default-planner stance.

## Current-State Audit

Before implementing this refactor, run a cheap source audit. Do not run new
Terminal-Bench proof spending for this design.

```bash
rg -n "DEFAULT_TOOL_SURFACE_PROFILE_ID|tool_surface_profile_id|tool_profile|codex_hot_path|mew_legacy" \
  src/mew/implement_lane src/mew/commands.py src/mew/mew_harbor_runner.py tests scripts

rg -n "experimental_finish_verifier_planner|finish_verifier_planner" \
  src/mew/commands.py src/mew/implement_lane/native_tool_harness.py tests scripts

rg -n "run_live_json_implement_v2|JsonModelProviderAdapter|model_json_callable|_live_json_prompt|_normalize_live_json_payload|history_json|frontier_state_update|implement_v2_model_json_tool_loop" \
  src/mew/commands.py src/mew/implement_lane tests scripts

rg -n "run_live_native_implement_v2|IMPLEMENT_V2_NATIVE_RUNTIME_ID|provider_native_tool_loop|model_json_main_path_detected" \
  src/mew/commands.py src/mew/implement_lane tests scripts

rg -n "(from \\.tool_profiles\\.mew_legacy import|from mew\\.implement_lane\\.tool_profiles\\.mew_legacy import|list_v2_(base_tool_specs|tool_specs_for_mode|tool_specs_for_task))" \
  src/mew scripts tests

rg -n "from \\.v2_runtime import|_render_prompt_history_json" \
  src/mew/implement_lane tests scripts

rg -n "__all__|run_live_json_implement_v2" \
  src/mew/implement_lane/v2_runtime.py src/mew/implement_lane/__init__.py tests/test_implement_lane.py
```

Inspect these files directly:

- `src/mew/commands.py`: selected-lane routing, work-guidance parsing,
  lane-config defaults, and persisted runtime metrics.
- `src/mew/mew_harbor_runner.py`: diagnostic/default command templates and
  flags that currently inject guidance.
- `src/mew/implement_lane/registry.py`: v2 runtime identity and capability
  contract.
- `src/mew/implement_lane/tool_registry.py`: profile default, option parsing,
  snapshot fields, route/profile hashes.
- `src/mew/implement_lane/tool_profiles/codex_hot_path.py`: desired default
  tool specs and developer contract.
- `src/mew/implement_lane/tool_profiles/mew_legacy.py`: legacy native profile
  that should become opt-out only.
- `src/mew/implement_lane/native_tool_harness.py`: native loop, request
  descriptor, tool-surface selection, planner eligibility, artifact writes,
  and current `list_v2_tool_specs_for_task` import.
- `src/mew/implement_lane/native_provider_adapter.py`: provider-native request
  descriptor, previous-response delta, stream parsing, and any accidental
  legacy-text transport coupling. Its default `tool_specs` fallback must not
  call `list_v2_base_tool_specs()` from `mew_legacy`.
- `src/mew/implement_lane/native_tool_schema.py`: provider-visible schema
  lowering; ensure no production finish/model-JSON schema is still selected.
- `src/mew/implement_lane/tool_routes.py`: route metadata for profile adapters,
  legacy finish, process lifecycle, and typed source mutation.
- `src/mew/implement_lane/substrate_inventory.py`: hardcoded `mew_legacy` base
  and mode spec inventory plus runtime-source labels that must remain accurate
  after the default switch.
- `src/mew/implement_lane/tool_harness_contract.py`: contract/default spec
  construction that currently bypasses active profile resolution.
- `src/mew/implement_lane/workframe_variant_transcript_tool_nav.py`:
  fallback tool-name resolution that currently imports `mew_legacy` base
  specs directly.
- `src/mew/implement_lane/tool_lab.py`: deterministic diagnostics that import
  `v2_runtime.py` helpers and may need a legacy-tool-lab or shared-helper split.
- `src/mew/implement_lane/hot_path_fastcheck.py`: fastcheck import of
  `_render_prompt_history_json` and artifact-level mixed-path checks.
- `src/mew/implement_lane/native_finish_gate.py`: finish command source order
  and internal closeout authority.
- `src/mew/implement_lane/completion_resolver.py`: sidecar-only resolver
  boundary.
- `src/mew/implement_lane/internal_finish_gate_contract.py`: contract naming
  and fixture expectations for internal finish behavior.
- `src/mew/implement_lane/native_validation.py`: static anti-drift gate.
- `src/mew/cli.py`: implement-v2 tool-lab command flags and any user-facing
  naming that implies hot path/profile selection is required.
- `src/mew/commands.py`, `src/mew/tool_kernel.py`, and
  `src/mew/implement_lane/__init__.py`: production-facing direct imports or
  package exports of `list_v2_*` functions that should move behind the active
  profile/tool registry or become legacy/test-only exports.
- `tests/test_implement_lane.py`: large legacy model-JSON coverage file; split
  or rename imports so native default tests no longer import
  `run_live_json_implement_v2`.
- `src/mew/terminal_bench_replay.py` and `src/mew/mew_harbor_runner.py`:
  read-only support for old and new artifacts.

Review related docs before changing code:

- `docs/DESIGN_2026-05-13_M6_24_CODEX_LIKE_NATIVE_HOT_PATH.md`
- `docs/DESIGN_2026-05-14_M6_24_TOOL_REGISTRY_AND_CODEX_HOT_PATH.md`
- `docs/DESIGN_2026-05-15_M6_24_FINISH_VERIFIER_PLANNER.md`
- `docs/DESIGN_2026-05-16_M6_24_NATIVE_FINISH_GATE_CLOSEOUT.md`
- `docs/DESIGN_2026-05-17_M6_24_INTERNAL_FINISH_GATE.md`
- `docs/DESIGN_2026-05-17_M6_24_TOOL_PROFILE_DEVELOPER_MESSAGE.md`
- `docs/REVIEW_2026-05-11_IMPLEMENT_V2_NATIVE_LOOP_DRIFT_PREVENTION.md`
- `docs/M6_24_STAGED_CLOSE_REPORT_2026-05-20.md`

## Explicit Defaults

### Tool Profile

Change the default profile boundary, not each caller:

```text
DEFAULT_TOOL_SURFACE_PROFILE_ID = CODEX_HOT_PATH_PROFILE_ID
```

`tool_surface_profile_id(lane_config)` should return `codex_hot_path` when
the caller omits the profile. It should still accept `mew_legacy` only as an
explicit override and should record why the override happened.

All tool-spec resolution must route through the active profile or tool
registry as well, including base, mode-specific, and task-specific variants.
Production code must not keep direct fallbacks such as
`list_v2_base_tool_specs()`, `list_v2_tool_specs_for_mode()`, or
`list_v2_tool_specs_for_task()` from `tool_profiles/mew_legacy.py`. The
default tool spec list for `native_provider_adapter.py`,
`substrate_inventory.py`, `tool_harness_contract.py`,
`native_tool_harness.py`, and `workframe_variant_transcript_tool_nav.py` must
come from the same `ToolSurfaceSnapshot` or profile resolver that selected
`codex_hot_path`.

Explicit `mew_legacy` opt-out remains valid, but it should be represented as
`tool_surface_profile_id=mew_legacy` and resolved by the active
profile/tool-registry APIs. A production caller should not opt out by importing
`tool_profiles.mew_legacy` directly.

Record these fields in every provider request inventory, proof manifest metric,
and route artifact:

```text
tool_surface_profile_id
tool_surface_profile_default: true|false
tool_surface_profile_selection_source: default|work_guidance|cli_override|legacy_opt_out|test_fixture
tool_surface_profile_hash
tool_surface_descriptor_hash
tool_surface_route_table_hash
tool_surface_prompt_contract_id
developer_contract_id
developer_contract_hash
```

### Provider/Loop

`run_live_native_implement_v2` is the only normal v2 live entry point. The
route in `commands.py` should remain native, and static tests should fail if
`commands.py` imports `run_live_json_implement_v2`, `JsonModelProviderAdapter`,
or model-JSON prompt/normalization helpers.

Production metrics and manifests must agree on:

```text
runtime_id = implement_v2_native_transcript_loop
transport_kind in {"provider_native", "provider_native_websocket"}
provider_native_tool_loop = true
model_json_main_path_detected = false
```

If native provider support is unavailable, v2 should return `unavailable` or
`blocked` with a separate `fallback_lane=implement_v1` hint. It must not run
the model-JSON loop under the v2 name.

### Finish Verifier Planner

Make the planner default explicit and rename the config away from
`experimental`:

```text
finish_verifier_planner_enabled default: true
finish_verifier_planner=false: explicit diagnostic opt-out
experimental_finish_verifier_planner: accepted temporarily as legacy alias
```

Implement this through one production policy helper, for example
`finish_verifier_planner_policy(lane_config)`, that canonicalizes legacy and
new keys:

```text
no planner key present -> enabled=true, source=default_enabled
finish_verifier_planner_enabled=false -> enabled=false, source=explicit_disabled
finish_verifier_planner=false -> enabled=false, source=explicit_disabled_legacy_alias
finish_verifier_planner=true -> enabled=true, source=explicit_enabled_alias
experimental_finish_verifier_planner=true -> enabled=true, source=explicit_enabled_legacy_alias
experimental_finish_verifier_planner=false -> enabled=false, source=explicit_disabled_legacy_alias
```

After the helper exists, production native code must not read
`lane_config.get("experimental_finish_verifier_planner")` or the new key
directly. `commands.py`, `_native_finish_verifier_planner_can_run()`,
`_finish_verifier_planner_loop_request()`, the request-enabled field, and the
planner eligibility gate should all consume the policy object so omission flips
from disabled to enabled while explicit false remains an opt-out.

Planner eligibility should still require the existing safety preconditions:
there must be relevant prior tool results, the provider must expose
`plan_finish_verifier_command`, a final verifier can be run through the current
tool surface, and closeout budget must exist.

Configured verifier remains higher precedence than planner. Planner remains a
command selector only; `native_finish_gate.py` remains the authority that
decides completion after the verifier command runs.

### CLI And Guidance Flags

The ordinary CLI/runner path should not require these:

```text
tool_surface_profile_id=codex_hot_path
finish_verifier_planner=true
```

Recommended flag stance:

- `mew work --work-guidance "selected_lane=implement_v2"` should use
  `codex_hot_path` and planner-enabled defaults.
- `finish_verifier_planner=true` becomes a no-op compatibility alias.
- `finish_verifier_planner=false` becomes an explicit diagnostic opt-out and
  must be recorded as `planner_selection_source=explicit_opt_out`.
- `--tool-surface-profile-id codex_hot_path` in `mew_harbor_runner.py` becomes
  a no-op compatibility override and should be removed from run names once
  callers no longer need it.
- `--tool-surface-profile-id mew_legacy` remains only for A/B, replay, or
  emergency native-profile rollback. Its help text should say legacy/diagnostic
  opt-out, not ordinary profile choice.
- Any future direct `mew work` profile flag should be named around override
  semantics, for example `--legacy-tool-surface mew_legacy`, rather than
  implying that callers must pick the standard profile.

## Mixed Native/Model-JSON Detection

Treat mixed behavior as a close-gate failure. Detect it at both source and
artifact levels.

### Source-Level Failure Signals

These symbols are allowed only in explicitly quarantined legacy modules,
legacy fixtures, replay readers, tests, or docs:

```text
run_live_json_implement_v2
JsonModelProviderAdapter
FakeProviderAdapter
FakeProviderToolCall
model_json_callable
_call_model_turn
_live_json_prompt
_normalize_live_json_payload
history_json
frontier_state_update
implement_v2_model_json_tool_loop
provider = "model_json"
_render_prompt_history_json
from .v2_runtime import
from .tool_profiles.mew_legacy import
from mew.implement_lane.tool_profiles.mew_legacy import
list_v2_base_tool_specs
list_v2_tool_specs_for_mode
list_v2_tool_specs_for_task
lane_config.get("experimental_finish_verifier_planner")
```

The helper, import, and config-key lines after `provider = "model_json"` are
not model-JSON entry points by themselves, but they are default-native refactor
hazards: production native modules must not import model-JSON-shaped helpers
from the quarantined runtime, bypass the active tool profile by importing
`mew_legacy` spec resolvers directly, or bypass the planner policy helper by
reading the legacy config key directly.

Production native paths to scan:

```text
src/mew/commands.py
src/mew/implement_lane/__init__.py
src/mew/implement_lane/registry.py
src/mew/implement_lane/native_provider_adapter.py
src/mew/implement_lane/native_tool_harness.py
src/mew/implement_lane/native_tool_schema.py
src/mew/implement_lane/tool_registry.py
src/mew/implement_lane/tool_routes.py
src/mew/implement_lane/tool_profiles/
src/mew/implement_lane/substrate_inventory.py
src/mew/implement_lane/tool_harness_contract.py
src/mew/implement_lane/workframe_variant_transcript_tool_nav.py
src/mew/implement_lane/tool_lab.py
src/mew/implement_lane/hot_path_fastcheck.py
src/mew/tool_kernel.py
```

The existing `native_validation.py` gate is the right place to add these
checks, because it already rejects legacy symbols in production native paths.

### Artifact-Level Failure Signals

A completed production v2 artifact is invalid if any of these are true:

- `proof-manifest.json.runtime_id == implement_v2_model_json_tool_loop`
- `transport_kind == model_json` or `legacy_model_json`
- `metrics.provider_native_tool_loop is not true`
- `metrics.model_json_main_path_detected is true`
- missing `response_transcript.json`
- missing or invalid call/output pairing
- request inventory has no provider-native `tools` descriptor hash
- request inventory says `tool_surface_profile_id=mew_legacy` without an
  explicit legacy override source
- provider-visible input includes model-JSON control fields such as
  `tool_calls`, `finish`, `history_json`, or `frontier_state_update`
- `codex_hot_path` request input includes the legacy JSON task envelope instead
  of the profile-owned developer contract plus raw task text

Add a cheap artifact audit command to the close gate:

```bash
python scripts/check_implement_v2_native_gate.py --source-root .
python scripts/check_implement_v2_hot_path.py --artifact <latest-native-artifact>
```

When no artifact is available, the native gate should still pass static route
and fixture checks, but the final close gate for a code change should include
at least one fake-native or saved-artifact verification.

## Refactor Phases

### Phase 0: Baseline Audit

Deliverables:

- Run the source audit commands above.
- Update `native_validation.py` expectations on paper before touching code.
- List every production file that still references legacy model-JSON symbols.
- List every production file that imports any `list_v2_*` tool-spec resolver
  directly from `tool_profiles/mew_legacy.py`; expected current entries
  include `native_provider_adapter.py`, `substrate_inventory.py`,
  `tool_harness_contract.py`, `native_tool_harness.py`,
  `workframe_variant_transcript_tool_nav.py`, `src/mew/commands.py`,
  `src/mew/tool_kernel.py`, and package exports in
  `src/mew/implement_lane/__init__.py`.
- List every production consumer of `v2_runtime.py` helpers; expected current
  entries include `native_tool_harness.py`, `tool_lab.py`, and
  `hot_path_fastcheck.py`.
- List every test that assumes missing `tool_surface_profile_id` means
  `mew_legacy`.
- List every test that assumes missing `finish_verifier_planner` means false.
- Inventory `tests/test_implement_lane.py` imports of
  `run_live_json_implement_v2`, `_render_prompt_history_json`, and
  `list_v2_base_tool_specs`, `list_v2_tool_specs_for_mode`, and
  `list_v2_tool_specs_for_task`; decide which tests are legacy model-JSON
  tests, which are shared-helper tests, and which should become native-default
  tests.

Close gate:

- No code change yet.
- Clear migration list for defaults, planner aliasing, and legacy quarantine.

### Phase 1: Central Default Profile Switch

Change only the central default boundary first:

- `tool_registry.py`: default `tool_surface_profile_id()` to
  `CODEX_HOT_PATH_PROFILE_ID`.
- Preserve explicit `mew_legacy` selection.
- Add selection-source metadata to `ToolSurfaceSnapshot` or the request
  metadata emitted from it.
- Route base, mode-specific, and task-specific tool specs through the active
  profile/tool registry. Migrate `native_provider_adapter.py`,
  `substrate_inventory.py`, `tool_harness_contract.py`,
  `native_tool_harness.py`, `workframe_variant_transcript_tool_nav.py`,
  `src/mew/commands.py`, `src/mew/tool_kernel.py`, and package exports away
  from hardcoded `mew_legacy` imports.
- Adjust `native_tool_harness.py` request inventory/proof metrics to carry the
  selection-source fields.
- Update tests that currently assert `mew_legacy` for omitted config to assert
  `codex_hot_path`.

Close gate:

- `build_tool_surface_snapshot(lane_config={...})` with no profile returns
  `codex_hot_path`.
- `mew_legacy` remains selectable only with explicit override.
- Provider request inventory proves profile id, developer contract, descriptor
  hash, and route-table hash.
- `rg -n "(from \\.tool_profiles\\.mew_legacy import|from mew\\.implement_lane\\.tool_profiles\\.mew_legacy import)" src/mew`
  has no production hits outside the profile registry, profile definitions,
  legacy-named quarantine modules, or tests.
- Explicit `mew_legacy` opt-out still works by selecting the profile id through
  the registry; no production path hardcodes it by direct import.
- No production request includes legacy task JSON for the default profile.

### Phase 2: CLI And Runner Defaults

Make callers stop spelling standard defaults:

- `commands.py`: construct `lane_config` with explicit default facts even when
  no work-guidance flags are present.
- `commands.py`: replace `experimental_finish_verifier_planner` as the primary
  key with `finish_verifier_planner_enabled=True`; keep the old key as an alias
  for one migration window.
- Add the planner policy helper here, even if Phase 4 later broadens tests and
  metrics. `commands.py` should write canonical default facts, but native
  harness eligibility must not depend on commands having injected a key.
- `mew_harbor_runner.py`: remove `finish_verifier_planner=true` from
  `DEFAULT_WORK_GUIDANCE` after `commands.py` owns the default.
- `mew_harbor_runner.py`: keep `--tool-surface-profile-id` as a legacy/diagnostic
  override and stop documenting it as required for the standard hot path.
- Tests in `tests/test_work_session.py` and `tests/test_mew_harbor_runner.py`
  should prove omission of these flags still selects native/codex/planner.

Close gate:

- `selected_lane=implement_v2` alone selects native, `codex_hot_path`, and
  planner-enabled defaults.
- Passing `finish_verifier_planner=true` produces the same lane config as
  omission except for optional compatibility metadata.
- Passing `finish_verifier_planner=false` disables planner and is recorded.
- Passing `mew_legacy` records a legacy opt-out source.
- Static audit has no direct production reads of
  `experimental_finish_verifier_planner` except inside the policy helper and
  migration tests.

### Phase 3: Legacy Model-JSON Quarantine

Move or rename legacy paths so the default implementation cannot accidentally
import them:

- Split `v2_runtime.py` into a production-neutral helper module plus an
  explicitly named legacy module, for example
  `legacy_model_json_runtime.py`.
- Move `JsonModelProviderAdapter` and model-JSON fake adapter names out of
  `provider.py` or rename the module to include `legacy_model_json`.
- Keep only pure helper functions still used by the native harness in
  production-safe modules. Current native imports from `v2_runtime.py`, such as
  finish/acceptance helpers, should move to a small shared helper module.
- Migrate current helper consumers explicitly:
  `native_tool_harness.py` imports `_acceptance_session_from_tool_results` and
  `_finish_acceptance_action`; move these to a production-safe
  `finish_acceptance_helpers.py` or equivalent. `tool_lab.py` imports
  `IMPLEMENT_V2_LANE`, `_first_write_readiness_from_trace`,
  `_provider_visible_tool_result_for_history`, and
  `run_fake_exec_implement_v2`; split deterministic diagnostic helpers into a
  production-safe tool-lab helper or a legacy-named tool-lab adapter.
  `hot_path_fastcheck.py` imports `_render_prompt_history_json`; move that to a
  legacy artifact renderer used only by replay/fastcheck fixtures, or replace
  the fastcheck projection with provider-native artifact parsing.
- Remove legacy exports from `src/mew/implement_lane/__init__.py`.
- Remove `run_live_json_implement_v2` and other legacy live-loop names from
  `v2_runtime.py.__all__` or move `__all__` with the renamed legacy module.
- Keep `terminal_bench_replay.py` support for historical model-JSON artifacts
  as read-only replay, with names that include `legacy_model_json`.
- Move or rename `tests/test_implement_lane.py` legacy live-loop coverage so it
  imports from `legacy_model_json_runtime.py`; native default tests should stop
  importing `run_live_json_implement_v2`.

Close gate:

- Static gate rejects legacy model-JSON symbols in production native paths.
- Legacy model-JSON tests import from legacy-named modules.
- Native production modules cannot import `v2_runtime.py` helpers whose data
  shape is model-JSON history, prompt projection, or legacy live-loop state.
- `tests/test_implement_lane.py` no longer mixes native-default assertions with
  direct legacy live-loop imports.
- No completed native result can report `implement_v2_model_json_tool_loop`.
- Replay of old artifacts still works and is explicitly labeled legacy.

### Phase 4: Planner Default Cleanup

Turn planner defaulting into a first-class policy:

- Replace `_native_finish_verifier_planner_can_run()` dependency on
  `experimental_finish_verifier_planner` with a default-enabled policy helper.
- Make the policy helper the single source of truth for the request-enabled
  field and eligibility gate. The helper must flip absent config to enabled and
  preserve explicit false as disabled.
- Keep configured verifier first, planner second, auto-detected verifier third.
- Preserve existing planner safety checks and artifact writes:
  `finish_verifier_planner_requests.jsonl`,
  `finish_verifier_planner_decisions.jsonl`, manifest refs, status counts, and
  fallback records.
- Add `planner_selection_source` metrics:
  `default_enabled`, `explicit_enabled_alias`, `explicit_disabled`,
  `not_eligible`, `provider_missing`, `configured_verifier_precedence`.

Close gate:

- Tests prove planner can run without guidance when eligible.
- Tests prove explicit opt-out prevents planner and records the opt-out.
- Existing safety tests still reject unsafe planner commands before dispatch.
- Planner failure still falls back only to safe auto-detected verifier, never to
  model-JSON or acceptance prose.
- Static validation rejects direct production reads of
  `experimental_finish_verifier_planner` or
  `finish_verifier_planner_enabled` outside the policy helper.

### Phase 5: Mixed-Path Gates And Observability

Extend validation rather than relying on convention:

- `native_validation.py`: add checks for default profile id, planner default
  policy, and legacy opt-out markers.
- `hot_path_fastcheck.py`: reject native artifacts whose default profile is not
  `codex_hot_path` unless the artifact explicitly marks legacy opt-out.
- `mew_harbor_runner.py` summary: include selected profile, selection source,
  planner enabled/selected/request counts, native runtime id, and mixed-path
  failure flags.
- `tool_routes.jsonl`: preserve per-route profile hashes and declared/effective
  tool names, especially `exec_command -> run_command` and
  `write_stdin -> poll_command`.

Close gate:

- Static native gate passes.
- Focused hot-path fastcheck passes on a native artifact or fixture.
- Manifest, request inventory, route records, and transcript metrics agree on
  profile id and hashes.
- No source or artifact path can silently mix native transport with model-JSON
  control objects.

### Phase 6: Deletion And Migration Map

After default/native/planner gates pass, delete or quarantine leftovers:

| Area | Current symbol or file | Target stance |
| --- | --- | --- |
| Legacy live loop | `run_live_json_implement_v2` in `v2_runtime.py` | Move to `legacy_model_json_runtime.py` or delete after replay migration. |
| Legacy provider adapter | `JsonModelProviderAdapter` in `provider.py` | Move to legacy/test module; no production export. |
| Generic provider fake | `FakeProviderAdapter`, `FakeProviderToolCall` | Keep only if tests need them, under test/legacy names. |
| Runtime literal | `implement_v2_model_json_tool_loop` | Allowed only in legacy replay/tests/docs. |
| Prompt protocol | `history_json`, `frontier_state_update`, model-authored `finish` | Delete from production; legacy replay only. |
| Default profile | `mew_legacy` implicit default | Explicit legacy opt-out only. |
| Legacy tool-spec resolver imports | `list_v2_base_tool_specs`, `list_v2_tool_specs_for_mode`, and `list_v2_tool_specs_for_task` direct imports in production helpers such as `native_provider_adapter.py`, `substrate_inventory.py`, `tool_harness_contract.py`, `native_tool_harness.py`, `workframe_variant_transcript_tool_nav.py`, `src/mew/commands.py`, and `src/mew/tool_kernel.py` | Resolve through active profile/tool registry; direct imports only in profile modules, tests, or legacy quarantine. Explicit `mew_legacy` opt-out remains a registry-selected profile id. |
| Package profile exports | `src/mew/implement_lane/__init__.py` exports `list_v2_base_tool_specs` and `list_v2_tool_specs_for_mode` | Remove production package exports or relabel as legacy/test-only; production callers use registry/profile snapshots. |
| Planner flag | `experimental_finish_verifier_planner` | Legacy alias; primary key is `finish_verifier_planner_enabled`. |
| Harbor profile flag | `--tool-surface-profile-id codex_hot_path` | No-op compatibility; remove from run naming after callers stop passing it. |
| Legacy profile | `tool_profiles/mew_legacy.py` | Keep as native A/B or emergency opt-out, not model-JSON fallback. |
| Runtime exports | `v2_runtime.py.__all__` includes `run_live_json_implement_v2` | Remove from production exports or move to `legacy_model_json_runtime.__all__`. |
| Native helper imports | `native_tool_harness.py`, `tool_lab.py`, `hot_path_fastcheck.py` import `v2_runtime.py` helpers | Move shared helpers to production-safe modules; model-JSON-shaped helpers stay legacy/replay only. |
| Legacy tests | `tests/test_implement_lane.py` imports `run_live_json_implement_v2` and `_render_prompt_history_json` | Split/rename as legacy model-JSON tests or shared-helper tests; native default tests import native entry points only. |

Close gate:

- Every remaining legacy symbol lives in a legacy-named module, test, replay
  reader, or doc.
- Production imports and package exports contain no generic model-JSON v2 entry
  points.
- Reviewer can grep the repo and immediately tell which paths are default
  native and which are legacy quarantine.

## Test Plan

Focused unit tests:

```bash
pytest tests/test_tool_registry.py
pytest tests/test_native_provider_adapter.py
pytest tests/test_native_tool_harness.py
pytest tests/test_native_validation.py
pytest tests/test_hot_path_fastcheck.py
pytest tests/test_work_session.py -k "implement_v2 or finish_verifier_planner or tool_surface"
pytest tests/test_mew_harbor_runner.py
```

Cheap static/script checks:

```bash
python scripts/check_implement_v2_native_gate.py --source-root .
python scripts/run_tool_surface_ab_smoke.py \
  --output-root proof-artifacts/tool-surface-ab-smoke/m6-25-default-native-refactor-smoke \
  --fixed-ab-set-id m6-24-tool-surface-smoke-v0 \
  --reviewer-accepted \
  --expect-ready
python scripts/check_tool_surface_default_switch_gate.py \
  --report <existing-tool-surface-ab-report-json> \
  --fixed-ab-set-id <fixed-ab-set-id-from-report> \
  --reviewer-accepted \
  --output proof-artifacts/tool-surface-ab-smoke/default-switch-gate.json
```

Only pass `--reviewer-accepted` or `--expect-ready` after a reviewer acceptance
note exists for the fixed A/B set. Without that note, omit
`--reviewer-accepted` and treat a non-ready gate as expected diagnostic output,
not a default-switch approval.

Artifact checks against existing or fake-native artifacts:

```bash
python scripts/check_implement_v2_hot_path.py --artifact <artifact-root-or-proof-manifest>
python scripts/analyze_provider_visible_salience.py \
  --mew-artifact-root <artifact-root> \
  --out-json <artifact-root>/provider-visible-salience.json \
  --out-md <artifact-root>/provider-visible-salience.md
python scripts/analyze_provider_continuity.py \
  --mew-artifact-root <artifact-root> \
  --out-json <artifact-root>/provider-continuity.json \
  --out-md <artifact-root>/provider-continuity.md
```

No close gate in this refactor should require new `proof_5` or speed-proof
spending. Live proof can be run later only if a named M6.25 experiment needs a
regression check.

## Observability And Proof Preservation

Do not reduce proof artifacts while changing defaults. Preserve:

- `response_transcript.json`
- `response_items.jsonl`
- `call_result_pairing.json`
- `transcript_metrics.json`
- `proof-manifest.json`
- `native-provider-requests.json`
- `provider-request-inventory.json`
- `tool_results.jsonl`
- `tool_result_index.json`
- `evidence_sidecar.json`
- `evidence_ref_index.json`
- `tool_routes.jsonl`
- `tool_render_outputs.jsonl`
- `done_candidates.jsonl`
- `native_finish_gate_decisions.jsonl`
- `native_ng_resume_signals.jsonl`
- `finish_verifier_planner_requests.jsonl`
- `finish_verifier_planner_decisions.jsonl`
- `native-evidence-observation.json`
- integration observer detail when enabled

Add or preserve proof fields that make defaults auditable:

```text
runtime_id
transport_kind
native_transport_kind
provider_native_tool_loop
model_json_main_path_detected
tool_surface_profile_id
tool_surface_profile_selection_source
tool_surface_profile_default
developer_contract_transport
finish_verifier_planner_enabled
finish_verifier_planner_selection_source
finish_verifier_planner_request_count
finish_verifier_planner_decision_count
previous_response_delta_mode
previous_response_prefix_item_count
provider_request_inventory_available
```

The default refactor is successful only if a reviewer can reconstruct, from
artifacts alone, that the run used provider-native tool calls, the default
Codex-like profile, internal finish closeout, and no model-JSON main path.

## Rollback And Compatibility

Rollback must not mean falling back to model-JSON inside v2.

Allowed rollback/compatibility:

- Explicitly select `mew_legacy` native profile for A/B, fixture comparison, or
  short-term emergency diagnostics.
- Disable planner with `finish_verifier_planner=false` for a targeted debug run.
- Route a failed v2 attempt to `implement_v1` as a separate fallback lane
  attempt.
- Read old model-JSON artifacts in replay and trace normalization, clearly
  labeled as legacy.

Disallowed rollback:

- Silent substitution of `run_live_json_implement_v2` when native provider
  support fails.
- Counting legacy model-JSON artifacts as native M6.25 evidence.
- Requiring normal users or runner scripts to pass `codex_hot_path` or
  `finish_verifier_planner=true` to get the intended standard path.
- Reopening M6.24 proof-spending or adding task-specific repair to justify the
  refactor.

## Non-Goals

- No new benchmark proof spending.
- No task-specific prompt tuning.
- No M6.24 reopening.
- No Doom/MIPS, Raman, Terminal-Bench, or benchmark-specific heuristic.
- No new provider-visible planner, `next_action`, `required_next`,
  `first_write_due`, WorkFrame action card, or renamed equivalent.
- No provider-visible finish schema in `codex_hot_path`.
- No weakening of write approval, command lifecycle, verifier freshness,
  transcript pairing, proof manifest hashing, or replay.
- No deletion of observability sidecars required by native replay and M6.24
  staged-close evidence.

## Reviewer Checklist

Reviewers should focus on:

- Does the plan make `codex_hot_path` the central default without scattering
  profile defaults across callers?
- Does it remove the need for ordinary hot-path/planner command-line guidance?
- Does it keep `mew_legacy` as explicit native opt-out rather than model-JSON
  fallback?
- Does every remaining model-JSON surface have a legacy/test/replay name?
- Are source-level and artifact-level mixed-path failures both covered?
- Are planner default, planner opt-out, and configured-verifier precedence
  testable?
- Are proof artifacts sufficient to audit the selected defaults after a run?
