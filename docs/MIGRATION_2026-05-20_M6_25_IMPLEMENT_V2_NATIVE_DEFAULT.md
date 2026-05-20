# M6.25 implement_v2 native default migration map

This map records the Phase 0-6 boundary after making provider-native
`codex_hot_path` the default `implement_v2` runtime path.

## Production native authority

- Runtime selection: `src/mew/implement_lane/registry.py` and
  `src/mew/commands.py` route production `implement_v2` to
  `implement_v2_native_transcript_loop`.
- Tool profile selection: `src/mew/implement_lane/tool_registry.py` owns the
  default profile. Missing profile config resolves to `codex_hot_path`.
- Planner selection: `src/mew/implement_lane/finish_verifier_planner_policy.py`
  owns planner enablement. Missing planner config resolves to enabled.
- Native artifacts: `proof-manifest.json`, `transcript_metrics.json`,
  `native-provider-requests.json`, `provider-request-inventory.json`, and
  `tool_routes.jsonl` carry profile, planner, native transport, and
  model-json absence facts.

## Quarantined legacy model-json surfaces

These remain only for legacy replay, migration tests, or explicit diagnostics:

- `src/mew/implement_lane/legacy_model_json_runtime.py`
- `src/mew/implement_lane/legacy_model_json_provider.py`
- `src/mew/implement_lane/legacy_model_json_tool_lab.py`
- `src/mew/implement_lane/v2_runtime.py`, labeled as quarantined legacy
  substrate and removed from production package exports.
- `src/mew/implement_lane/tool_profiles/mew_legacy.py`, selectable only by
  explicit native diagnostic opt-out.
- `src/mew/terminal_bench_replay.py`, read-only replay of historical artifacts.

## Static guards

- `scripts/check_implement_v2_native_gate.py` rejects production native paths
  that import or expose legacy model-json entry points.
- The native gate verifies default `codex_hot_path`, explicit `mew_legacy`
  opt-out markers, default-enabled planner policy, and no direct planner
  enablement reads outside the policy boundary.
- `run_hot_path_fastcheck()` rejects native artifacts whose default profile is
  not `codex_hot_path`, unless the artifact records `mew_legacy` as an explicit
  `legacy_opt_out`.

## Deferred deletion

Deleting the remaining legacy live-loop substrate is intentionally deferred
until replay tests and legacy model-json tests are split from
`tests/test_implement_lane.py`. Until then, legacy support is read-only or
explicitly selected, and production cannot silently fall back to model-json.
