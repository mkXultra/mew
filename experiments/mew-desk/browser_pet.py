from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any, TextIO


MAX_FOCUS_LENGTH = 160

PET_FRAMES: dict[str, list[str]] = {
    "sleeping": [
        " /\\_/\\",
        r"( -.- )",
        r" > ^ <",
    ],
    "thinking": [
        " /\\_/\\",
        r"( o.o )",
        r" > ? <",
    ],
    "typing": [
        " /\\_/\\",
        r"( o.o )",
        " />#<\\",
    ],
    "alerting": [
        " /\\_/\\",
        r"( O.O )",
        r" > ! <",
    ],
}

STATE_COPY: dict[str, str] = {
    "sleeping": "Quiet",
    "thinking": "Thinking",
    "typing": "Working",
    "alerting": "Needs input",
}


def normalize_pet_state(value: Any) -> str:
    if not isinstance(value, str):
        return "sleeping"
    state = value.strip().casefold()
    if state in PET_FRAMES:
        return state
    return "sleeping"


def compact_focus(value: Any) -> str:
    focus = " ".join(str(value or "No focus recorded").split())
    if len(focus) <= MAX_FOCUS_LENGTH:
        return focus
    return focus[: MAX_FOCUS_LENGTH - 3].rstrip() + "..."


def safe_count(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, str):
        try:
            return max(0, int(value.strip()))
        except ValueError:
            return 0
    return 0


def load_view_model(source: Path | None, stdin: TextIO = sys.stdin) -> dict[str, Any]:
    if source is None or str(source) == "-":
        raw = stdin.read()
    else:
        raw = source.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("view model JSON must be an object")
    return data


def count_items(view_model: dict[str, Any]) -> dict[str, int]:
    counts = view_model.get("counts")
    if not isinstance(counts, dict):
        counts = {}
    return {
        "tasks": safe_count(counts.get("open_tasks")),
        "questions": safe_count(counts.get("open_questions")),
        "sessions": safe_count(counts.get("active_work_sessions")),
        "attention": safe_count(counts.get("open_attention")),
    }


def render_count_items(counts: dict[str, int]) -> str:
    labels = [
        ("tasks", "Tasks"),
        ("questions", "Questions"),
        ("sessions", "Sessions"),
        ("attention", "Attention"),
    ]
    return "\n".join(
        f'<li><span>{html.escape(label)}</span><strong>{counts[key]}</strong></li>'
        for key, label in labels
    )


def render_browser_pet(view_model: dict[str, Any]) -> str:
    state = normalize_pet_state(view_model.get("pet_state"))
    focus = compact_focus(view_model.get("focus"))
    date = str(view_model.get("date") or "")
    counts = count_items(view_model)
    cat = "\n".join(PET_FRAMES[state])
    count_nodes = render_count_items(counts)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>mew desk</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #20231f;
      --muted: #5c665a;
      --panel: #ffffff;
      --line: #d9dfd6;
      --field: #f4f7f1;
      --green: #2f7d5b;
      --coral: #c94d3f;
      --yellow: #e2b93b;
      --blue: #3578a8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      background: var(--field);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    main {{
      width: min(440px, 100%);
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 12px 32px rgba(32, 35, 31, 0.12);
      overflow: hidden;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      align-items: center;
    }}
    h1 {{
      margin: 0;
      font-size: 18px;
      line-height: 1.2;
    }}
    .date {{
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }}
    .stage {{
      display: grid;
      gap: 14px;
      padding: 22px 18px 18px;
    }}
    .pet {{
      display: grid;
      justify-items: center;
      gap: 10px;
      padding: 20px 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfa;
    }}
    .cat {{
      margin: 0;
      font: 700 28px/1.05 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      letter-spacing: 0;
      white-space: pre;
    }}
    .state {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 8px;
      border: 1px solid var(--line);
      padding: 7px 10px;
      font-size: 13px;
      font-weight: 700;
    }}
    .state::before {{
      content: "";
      width: 10px;
      height: 10px;
      border-radius: 4px;
      background: var(--green);
    }}
    main[data-state="thinking"] .state::before {{ background: var(--blue); }}
    main[data-state="typing"] .state::before {{ background: var(--yellow); }}
    main[data-state="alerting"] .state::before {{ background: var(--coral); }}
    .focus {{
      margin: 0;
      color: var(--ink);
      line-height: 1.45;
      overflow-wrap: anywhere;
    }}
    ul {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    li {{
      display: grid;
      gap: 4px;
      padding: 12px 8px;
      border-right: 1px solid var(--line);
      min-width: 0;
      text-align: center;
    }}
    li:last-child {{ border-right: 0; }}
    li span {{
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    li strong {{
      font-size: 19px;
      line-height: 1;
    }}
    @media (max-width: 420px) {{
      body {{ padding: 12px; }}
      header {{ align-items: flex-start; flex-direction: column; }}
      .date {{ white-space: normal; }}
      ul {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      li:nth-child(2) {{ border-right: 0; }}
      li:nth-child(-n+2) {{ border-bottom: 1px solid var(--line); }}
      .cat {{ font-size: 24px; }}
    }}
  </style>
</head>
<body>
  <main data-state="{html.escape(state, quote=True)}">
    <header>
      <h1>mew desk</h1>
      <div class="date">{html.escape(date) or "local view"}</div>
    </header>
    <section class="stage" aria-label="mew status">
      <div class="pet">
        <pre class="cat" aria-hidden="true">{html.escape(cat)}</pre>
        <div class="state">{html.escape(STATE_COPY[state])}</div>
      </div>
      <p class="focus">{html.escape(focus)}</p>
      <ul aria-label="counts">
        {count_nodes}
      </ul>
    </section>
  </main>
</body>
</html>
"""


def main(argv: list[str] | None = None, stdin: TextIO = sys.stdin) -> int:
    parser = argparse.ArgumentParser(description="Render a mew desk view model as standalone browser HTML")
    parser.add_argument(
        "view_model",
        nargs="?",
        type=Path,
        help="path to a mew desk JSON view model; omit or pass - to read stdin",
    )
    parser.add_argument("--output", type=Path, help="write HTML to this path instead of stdout")
    args = parser.parse_args(argv)

    view_model = load_view_model(args.view_model, stdin=stdin)
    rendered = render_browser_pet(view_model)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
