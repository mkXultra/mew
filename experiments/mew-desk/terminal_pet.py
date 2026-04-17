from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO


PET_FRAMES: dict[str, list[str]] = {
    "sleeping": [
        r" /\_/\  z",
        r"( -.- )",
        r" > ^ < ",
    ],
    "thinking": [
        r" /\_/\  ?",
        r"( o.o )",
        r" > ? < ",
    ],
    "typing": [
        r" /\_/\  *",
        r"( o.o )",
        r" />#<\ ",
    ],
    "alerting": [
        r" /\_/\  !",
        r"( O.O )",
        r" > ! < ",
    ],
}


def normalize_pet_state(value: Any) -> str:
    if not isinstance(value, str):
        return "sleeping"
    state = value.strip().casefold()
    if state in PET_FRAMES:
        return state
    return "sleeping"


def load_view_model(source: Path | None, stdin: TextIO = sys.stdin) -> dict[str, Any]:
    if source is None or str(source) == "-":
        raw = stdin.read()
    else:
        raw = source.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("view model JSON must be an object")
    return data


def render_terminal_pet(view_model: dict[str, Any]) -> str:
    state = normalize_pet_state(view_model.get("pet_state"))
    focus = " ".join(str(view_model.get("focus") or "No focus recorded").split())
    counts = view_model.get("counts")
    if not isinstance(counts, dict):
        counts = {}
    count_line = "tasks={tasks} questions={questions} sessions={sessions} attention={attention}".format(
        tasks=int(counts.get("open_tasks") or 0),
        questions=int(counts.get("open_questions") or 0),
        sessions=int(counts.get("active_work_sessions") or 0),
        attention=int(counts.get("open_attention") or 0),
    )
    lines = [
        f"mew desk :: {state}",
        *PET_FRAMES[state],
        f"focus: {focus}",
        count_line,
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None, stdin: TextIO = sys.stdin) -> int:
    parser = argparse.ArgumentParser(description="Render a mew desk view model as a tiny terminal pet")
    parser.add_argument(
        "view_model",
        nargs="?",
        type=Path,
        help="path to a mew desk JSON view model; omit or pass - to read stdin",
    )
    args = parser.parse_args(argv)

    view_model = load_view_model(args.view_model, stdin=stdin)
    sys.stdout.write(render_terminal_pet(view_model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
