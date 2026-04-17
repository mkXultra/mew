from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ReportSpec:
    key: str
    title: str
    relative_path_template: str


@dataclass
class OutputPaths:
    bundle: Path


REPORTS = (
    ReportSpec("journal", "Journal", ".mew/journal/{day}.md"),
    ReportSpec("mood", "Mood", ".mew/mood/{day}.md"),
    ReportSpec("morning-paper", "Morning Paper", ".mew/morning-paper/{day}.md"),
    ReportSpec("dream", "Dream", ".mew/dreams/{day}.md"),
    ReportSpec("self-memory", "Self Memory", ".mew/self/learned-{day}.md"),
)


def resolve_date(explicit_date: str | None = None) -> str:
    if explicit_date:
        return explicit_date
    return datetime.now().date().isoformat()


def build_paths(output_dir: Path, day: str) -> OutputPaths:
    return OutputPaths(bundle=output_dir / ".mew" / "passive-bundle" / f"{day}.md")


def report_path(root: Path, spec: ReportSpec, day: str) -> Path:
    return root / spec.relative_path_template.format(day=day)


def strip_h1(markdown: str) -> str:
    lines = markdown.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        if lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip()


def first_non_empty_line(markdown: str) -> str:
    for line in markdown.splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            return text
    return ""


def collect_reports(root: Path, day: str) -> tuple[list[tuple[ReportSpec, Path, str]], list[ReportSpec]]:
    found = []
    missing = []
    for spec in REPORTS:
        path = report_path(root, spec, day)
        if path.exists() and path.is_file():
            found.append((spec, path, path.read_text(encoding="utf-8")))
        else:
            missing.append(spec)
    return found, missing


def render_bundle(day: str, found: list[tuple[ReportSpec, Path, str]], missing: list[ReportSpec]) -> str:
    lines = [
        f"# Mew Passive Bundle {day}",
        "",
        "## Summary",
    ]
    if found:
        lines.append("- included: " + ", ".join(spec.title for spec, _, _ in found))
    else:
        lines.append("- included: none")
    if missing:
        lines.append("- missing: " + ", ".join(spec.title for spec in missing))
    else:
        lines.append("- missing: none")

    lines.extend(["", "## Reentry hints"])
    if found:
        for spec, path, content in found:
            hint = first_non_empty_line(content)
            if hint:
                lines.append(f"- {spec.title}: {hint}")
            else:
                lines.append(f"- {spec.title}: {path}")
    else:
        lines.append("- No reports found; generate journal, mood, or morning-paper first")

    for spec, path, content in found:
        body = strip_h1(content)
        lines.extend(["", f"## {spec.title}", "", f"Source: `{path}`"])
        if body:
            lines.extend(["", body])
        else:
            lines.append("- Empty report")
    return "\n".join(lines) + "\n"


def write_outputs(paths: OutputPaths, text: str) -> None:
    paths.bundle.parent.mkdir(parents=True, exist_ok=True)
    paths.bundle.write_text(text, encoding="utf-8")


def generate(reports_root: Path, output_dir: Path, explicit_date: str | None = None) -> OutputPaths:
    day = resolve_date(explicit_date)
    found, missing = collect_reports(reports_root, day)
    paths = build_paths(output_dir, day)
    write_outputs(paths, render_bundle(day, found, missing))
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compose existing mew daily reports into one passive bundle")
    parser.add_argument("--reports-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--date")
    args = parser.parse_args(argv)

    paths = generate(args.reports_root, args.output_dir, args.date)
    print(paths.bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
