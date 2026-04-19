from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

from .report_io import write_generated_report


@dataclass(frozen=True)
class ReportSpec:
    key: str
    title: str
    relative_path_template: str


@dataclass
class BundleResult:
    path: Path
    text: str
    included: list[str]
    missing: list[str]


REPORTS = (
    ReportSpec("journal", "Journal", ".mew/journal/{day}.md"),
    ReportSpec("mood", "Mood", ".mew/mood/{day}.md"),
    ReportSpec("morning-paper", "Morning Paper", ".mew/morning-paper/{day}.md"),
    ReportSpec("dream", "Dream", ".mew/dreams/{day}.md"),
    ReportSpec("self-memory", "Self Memory", ".mew/self/learned-{day}.md"),
)

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date(value: str) -> str:
    if not DATE_PATTERN.fullmatch(value):
        raise ValueError("date must be in YYYY-MM-DD format")
    return value


def resolve_bundle_date(explicit_date: str | None = None) -> str:
    if explicit_date:
        return validate_date(explicit_date)
    return validate_date(datetime.now().date().isoformat())


def bundle_path(output_dir: Path, day: str) -> Path:
    return output_dir / ".mew" / "passive-bundle" / f"{day}.md"


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
    fallback_heading = ""
    for line in strip_h1(markdown).splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("#"):
            fallback_heading = fallback_heading or text.lstrip("#").strip()
            continue
        return text
    return fallback_heading


def first_line_in_section(markdown: str, heading: str) -> str:
    wanted = heading.strip().casefold()
    in_section = False
    for line in strip_h1(markdown).splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("## "):
            in_section = text.lstrip("#").strip().casefold() == wanted
            continue
        if text.startswith("#"):
            if in_section:
                break
            continue
        if not in_section:
            continue
        if text.startswith("- "):
            text = text[2:].strip()
        return text
    return ""


def reentry_hint(markdown: str) -> str:
    return first_line_in_section(markdown, "Continuity risks") or first_non_empty_line(markdown)


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
            hint = reentry_hint(content)
            lines.append(f"- {spec.title}: {hint or path}")
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


def generate_bundle(reports_root: Path, output_dir: Path, explicit_date: str | None = None) -> BundleResult:
    day = resolve_bundle_date(explicit_date)
    found, missing = collect_reports(reports_root, day)
    text = render_bundle(day, found, missing)
    path = bundle_path(output_dir, day)
    write_generated_report(path, text)
    return BundleResult(
        path=path,
        text=text,
        included=[spec.title for spec, _, _ in found],
        missing=[spec.title for spec in missing],
    )
