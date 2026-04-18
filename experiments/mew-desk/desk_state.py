from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from mew.desk import build_desk_view_model, render_desk_markdown


@dataclass
class OutputPaths:
    json_path: Path
    markdown_path: Path


def load_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_date(state: dict[str, Any], explicit_date: str | None = None) -> str:
    if explicit_date:
        return explicit_date
    for key in ("date", "today", "current_date"):
        value = state.get(key)
        if isinstance(value, str) and value:
            return value
    return datetime.now().date().isoformat()


def build_paths(output_dir: Path, day: str) -> OutputPaths:
    base = output_dir / ".mew" / "desk"
    return OutputPaths(json_path=base / f"{day}.json", markdown_path=base / f"{day}.md")


def build_view_model(day: str, state: dict[str, Any]) -> dict[str, Any]:
    return build_desk_view_model(state, explicit_date=day)


def render_markdown(view_model: dict[str, Any]) -> str:
    return render_desk_markdown(view_model)


def write_outputs(paths: OutputPaths, view_model: dict[str, Any]) -> None:
    paths.json_path.parent.mkdir(parents=True, exist_ok=True)
    paths.json_path.write_text(json.dumps(view_model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths.markdown_path.write_text(render_markdown(view_model), encoding="utf-8")


def generate(state_path: Path, output_dir: Path, explicit_date: str | None = None) -> OutputPaths:
    state = load_state(state_path)
    day = resolve_date(state, explicit_date)
    paths = build_paths(output_dir, day)
    write_outputs(paths, build_view_model(day, state))
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a mew desktop-pet view model from state JSON")
    parser.add_argument("state_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--date")
    args = parser.parse_args(argv)

    paths = generate(args.state_path, args.output_dir, args.date)
    print(paths.json_path)
    print(paths.markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
