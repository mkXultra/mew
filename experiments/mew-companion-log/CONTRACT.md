# Companion export contract

This experiment exposes a stable, local-only markdown export contract for `companion_log.py`. It is intentionally scoped to files under `experiments/mew-companion-log`.

## Boundaries

- Inputs are explicit JSON fixture files passed on the command line.
- Outputs are deterministic markdown written to stdout or to the path supplied by `--output`.
- The script must not import `src/mew`, read live `.mew` state, query GitHub live, use the network, or crawl the filesystem.
- Bundle mode may read only the explicit local fixture paths declared by `fixtures/sample_bundle.json`.
- Archive and dogfood modes render static fixture summaries only; their issue URLs and state-like rows are fixture data, not live lookups.

## CLI output behavior

All modes accept this shape:

```bash
python companion_log.py FIXTURE.json --mode MODE --output output.md
```

When `--output` is omitted, markdown is printed to stdout. When `--output` is present, the same markdown is written as UTF-8 text to the requested file. The documented contract for every mode is that the written file exists, starts with a markdown heading, and ends with a newline.

`report` is the default mode, so this is equivalent to `--mode report`:

```bash
python companion_log.py fixtures/sample_session.json --output report.md
```

## Mode contracts

| Mode | Fixture | Stable input schema | Stable markdown surface |
| --- | --- | --- | --- |
| `report` | `fixtures/sample_session.json` | Session object with `title`, `date`, task/status fields, recent notes, and next-action data. | Companion report headed by `# Companion Log:` with session summary and next actions. |
| `morning-journal` | `fixtures/sample_session.json` | Same session fixture plus morning planning fields such as focus, priorities, risks, and schedule cues. | Morning journal headed by `# Morning Journal:` for planning the day from static session data. |
| `evening-journal` | `fixtures/sample_session.json` | Same session fixture plus completion/reflection fields, outcomes, blockers, and follow-up notes. | Evening journal headed by `# Evening Journal:` for end-of-day reflection from static session data. |
| `dream-learning` | `fixtures/sample_session.json` | Same session fixture plus dream/learning prompts, learning signals, and carry-forward items. | Dream learning note headed by `# Dream Learning:` with learning prompts and next signals. |
| `research-digest` | `fixtures/sample_session.json` | Static research feed entries embedded in the fixture; no external feed or network lookup. | Research digest headed by `# Research Digest:` with ranked local research items. |
| `state-brief` | `fixtures/sample_mew_state.json` | Static mew-state-like object with project/session summaries, blockers, and next actions. | State companion brief headed by `# Mew State Companion Brief:` without reading live `.mew` state. |
| `bundle` | `fixtures/sample_bundle.json` | Bundle manifest with `id`, `title`, `date`, and `entries[]` containing `label`, `group`, `fixture`, `mode`, and `surface`. | Companion bundle headed by `# Companion Bundle:` that groups explicit local fixture renders. |
| `archive-index` | `fixtures/sample_archive.json` | Archive manifest with `id`, `title`, `date`, `summary`, and `days[]`; each entry has `day`, `surface`, `fixture`, `mode`, `title`, `summary`, and `next_action`. | Archive index headed by `# Companion Archive Index:` ordered by day and grouped by archived surface. |
| `dogfood-digest` | `fixtures/sample_dogfood_digest.json` | Dogfood digest object with `dogfood_rows`, `product_progress`, `blockers`, `m6_16_polish_candidates`, and `side_pj_issues`. | Dogfood digest headed by `# Dogfood Digest:` summarizing static rows, polish candidates, and fixture issue summaries. |

## Local schema examples

The fixture files are the schema examples for this experiment:

- `fixtures/sample_session.json` covers `report`, `morning-journal`, `evening-journal`, `dream-learning`, and `research-digest`.
- `fixtures/sample_mew_state.json` covers `state-brief`.
- `fixtures/sample_bundle.json` covers `bundle` and declares only explicit local fixture paths.
- `fixtures/sample_archive.json` covers `archive-index` and lists archived fixture names as static data.
- `fixtures/sample_dogfood_digest.json` covers `dogfood-digest`, including local dogfood rows, ledger-like progress/blocker summaries, reusable M6.16 polish candidates, and static `[side-pj]` issue summaries.

Tests in `tests/test_companion_log.py` are the compatibility gate for this contract: every documented mode must continue to render and write a markdown output file from its local fixture.
