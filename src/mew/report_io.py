from __future__ import annotations

from pathlib import Path


def backup_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.bak")


def write_generated_report(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_file():
        previous = path.read_text(encoding="utf-8")
        if previous != text:
            backup = backup_path(path)
            if not backup.exists():
                backup.write_text(previous, encoding="utf-8")
    path.write_text(text, encoding="utf-8")
