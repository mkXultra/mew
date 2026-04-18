from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from browser_pet import DEFAULT_REFRESH_SECONDS, load_view_model, render_browser_pet  # noqa: E402
from browser_server import CommandViewModelSource  # noqa: E402


DEFAULT_INTERVAL_SECONDS = 5.0


class ViewModelSource(Protocol):
    def load(self) -> dict[str, Any]:
        pass


class FileViewModelSource:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        return load_view_model(self.path)


@dataclass
class RenderOnceResult:
    wrote: bool
    error: str = ""


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
    return True


def render_once(source: ViewModelSource, output: Path, refresh_seconds: int) -> RenderOnceResult:
    try:
        view_model = source.load()
        rendered = render_browser_pet(view_model, refresh_seconds=refresh_seconds)
        wrote = write_if_changed(output, rendered)
    except Exception as exc:
        return RenderOnceResult(wrote=False, error=f"{type(exc).__name__}: {exc}")
    return RenderOnceResult(wrote=wrote)


def watch(
    source: ViewModelSource,
    output: Path,
    interval_seconds: float,
    refresh_seconds: int,
    *,
    sleep: Callable[[float], None] = time.sleep,
    iterations: int | None = None,
) -> None:
    completed = 0
    while iterations is None or completed < iterations:
        result = render_once(source, output, refresh_seconds)
        if result.error:
            print(result.error, file=sys.stderr, flush=True)
        elif result.wrote:
            print(str(output), flush=True)
        completed += 1
        if iterations is not None and completed >= iterations:
            break
        sleep(interval_seconds)


def build_source(args: argparse.Namespace) -> ViewModelSource:
    if args.source_command:
        return CommandViewModelSource(args.source_command, timeout=args.command_timeout)
    if args.source:
        return FileViewModelSource(args.source)
    raise ValueError("provide a source path or --source-command")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Continuously render a mew desk browser HTML file")
    parser.add_argument("source", nargs="?", type=Path, help="path to a mew desk JSON view model")
    parser.add_argument("--output", required=True, type=Path, help="HTML file to update atomically")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--refresh-seconds", type=int, default=DEFAULT_REFRESH_SECONDS)
    parser.add_argument("--command-timeout", type=float, default=10.0)
    parser.add_argument(
        "--source-command",
        nargs=argparse.REMAINDER,
        help="command that prints a mew desk JSON object; put this option last",
    )
    args = parser.parse_args(argv)
    if args.interval <= 0:
        parser.error("--interval must be greater than 0")
    if args.refresh_seconds < 1:
        parser.error("--refresh-seconds must be at least 1")

    try:
        source = build_source(args)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        watch(source, args.output, args.interval, args.refresh_seconds)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
