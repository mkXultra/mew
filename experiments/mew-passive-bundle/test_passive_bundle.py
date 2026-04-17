from __future__ import annotations

import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("passive_bundle.py")
SPEC = importlib.util.spec_from_file_location("passive_bundle", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
passive_bundle = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = passive_bundle
SPEC.loader.exec_module(passive_bundle)


def write_report(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_generate_composes_existing_reports(tmp_path: Path) -> None:
    write_report(
        tmp_path,
        ".mew/journal/2026-04-17.md",
        "# Mew Journal 2026-04-17\n\nCurrent work: ship journal.\n",
    )
    write_report(
        tmp_path,
        ".mew/mood/2026-04-17.md",
        "# Mew Mood 2026-04-17\n\nCurrent mood: **steady**\n",
    )

    paths = passive_bundle.generate(tmp_path, tmp_path, explicit_date="2026-04-17")
    text = paths.bundle.read_text()

    assert paths.bundle == tmp_path / ".mew" / "passive-bundle" / "2026-04-17.md"
    assert "# Mew Passive Bundle 2026-04-17" in text
    assert "- included: Journal, Mood" in text
    assert "- missing: Morning Paper, Dream, Self Memory" in text
    assert "- Journal: Current work: ship journal." in text
    assert "- Mood: Current mood: **steady**" in text
    assert "## Journal" in text
    assert "## Mood" in text
    assert "# Mew Journal" not in text


def test_generate_handles_no_reports(tmp_path: Path) -> None:
    paths = passive_bundle.generate(tmp_path, tmp_path, explicit_date="2026-04-17")
    text = paths.bundle.read_text()

    assert "- included: none" in text
    assert "- No reports found; generate journal, mood, or morning-paper first" in text


def test_main_prints_created_path(tmp_path: Path) -> None:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = passive_bundle.main(
            ["--reports-root", str(tmp_path), "--output-dir", str(tmp_path), "--date", "2026-04-17"]
        )

    assert exit_code == 0
    assert stdout.getvalue().strip() == str(tmp_path / ".mew" / "passive-bundle" / "2026-04-17.md")
