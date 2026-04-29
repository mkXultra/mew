# SP24a live desk human cat proof

Date: 2026-04-29
Scope: experiments/mew-ghost only

## Slice

Prove the CLI-first mew-wisp human terminal cat surface can render explicit live desk adapter output through the existing opt-in injected `desk_provider` / `--live-desk` path, not only through static `--desk-json` fixtures.

## Patch summary

- Adds a focused pytest that calls `ghost.run_watch(..., desk_provider=provider, format_name='human', terminal_form='cat')` with an explicit live-desk-shaped status/action payload.
- Asserts the cat speech bubble is preserved and stays separate from the resident HUD.
- Asserts the resident HUD carries the injected live desk action.
- Asserts `--details` gates freshness, desk details, active window, and launcher-intent diagnostics.
- Asserts live desk status/action markers are visible in detailed human cat output.
- Asserts the proof does not depend on the static `sample_desk_view.json` / `--desk-json` fixture path.

## Safety boundary

No `ghost.py` source change is proposed in this slice. The proof remains opt-in through injected live desk status; it does not add background monitoring, hidden `.mew` reads, new shell execution, core imports, or launcher execution.

## Verifier

`UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`

Result: `41 passed in 0.03s`
