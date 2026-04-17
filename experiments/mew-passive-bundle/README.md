# mew-passive-bundle

Small CLI-first experiment that composes already-generated mew daily reports
into one dated passive bundle.

Output:

- `.mew/passive-bundle/YYYY-MM-DD.md`

This experiment does not generate source reports. It only reads the reports that
already exist under a local `.mew` root:

- `.mew/journal/YYYY-MM-DD.md`
- `.mew/mood/YYYY-MM-DD.md`
- `.mew/morning-paper/YYYY-MM-DD.md`
- `.mew/dreams/YYYY-MM-DD.md`
- `.mew/self/learned-YYYY-MM-DD.md`

The goal is to test the integration surface before promoting any individual
report into a core command.

## Usage

First generate one or more reports, for example:

```bash
uv run python experiments/mew-journal/journal_report.py .mew/state.json --output-dir /tmp/mew-daily
uv run python experiments/mew-mood/mood_report.py .mew/state.json --output-dir /tmp/mew-daily
uv run python experiments/mew-morning-paper/morning_paper.py experiments/mew-morning-paper/sample_feed.json --state-path experiments/mew-morning-paper/sample_state.json --output-dir /tmp/mew-daily
```

Then compose the bundle:

```bash
uv run python experiments/mew-passive-bundle/passive_bundle.py --reports-root /tmp/mew-daily --output-dir /tmp/mew-daily --date 2026-04-17
```

Read the generated bundle:

```bash
cat /tmp/mew-daily/.mew/passive-bundle/2026-04-17.md
```

## Test

```bash
uv run pytest -q experiments/mew-passive-bundle
```
