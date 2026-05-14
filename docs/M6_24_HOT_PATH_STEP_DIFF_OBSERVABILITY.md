# M6.24 Hot-Path Step-Diff Observability

Before spending another same-shape `step-check-10min`, compare the saved Codex
reference trace against the latest saved mew artifact with the sidecar analyzer:

```bash
uv run python scripts/analyze_hot_path_step_diff.py \
  --codex-reference-root <codex-reference-root> \
  --mew-artifact-root <mew-artifact-root> \
  --out-json tmp/hot-path-step-diff.json \
  --out-md tmp/hot-path-step-diff.md
```

The tool is artifact-only. It reads normalized Codex trace files and mew native
loop artifacts, then reports first mutation timing, probe counts before mutation,
repeated probe families, debug-only tool intent classifications, and possible
first-patch opportunities with cited trace rows. It must not be wired into live
provider behavior or task-specific rules.
