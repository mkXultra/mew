from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO


MAX_FOCUS_LENGTH = 96


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


def render_terminal_pet(view_model: dict[str, Any]) -> str:
    state = normalize_pet_state(view_model.get("pet_state"))
    focus = compact_focus(view_model.get("focus"))
    counts = view_model.get("counts")
    if not isinstance(counts, dict):
        counts = {}
    count_line = "tasks={tasks} questions={questions} sessions={sessions} attention={attention}".format(
        tasks=safe_count(counts.get("open_tasks")),
        questions=safe_count(counts.get("open_questions")),
        sessions=safe_count(counts.get("active_work_sessions")),
        attention=safe_count(counts.get("open_attention")),
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
