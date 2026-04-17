# mew-morning-paper

Small CLI-first experiment that ranks a static feed against local interest tags
and generates a dated morning paper markdown report.

Output:

- `.mew/morning-paper/YYYY-MM-DD.md`

This first slice does not fetch the network. It uses fixture JSON so the product
question can be tested safely: can mew choose useful reading material from a
larger stream when it knows a few interests?

## Usage

```bash
uv run python experiments/mew-morning-paper/morning_paper.py experiments/mew-morning-paper/sample_feed.json --state-path experiments/mew-morning-paper/sample_state.json --output-dir /tmp/mew-morning-paper
```

Use explicit interest tags without a state file:

```bash
uv run python experiments/mew-morning-paper/morning_paper.py experiments/mew-morning-paper/sample_feed.json --interest passive-ai --interest memory --output-dir /tmp/mew-morning-paper
```

Read the generated report:

```bash
cat /tmp/mew-morning-paper/.mew/morning-paper/2026-04-17.md
```

## Test

```bash
uv run pytest -q experiments/mew-morning-paper
```
