from __future__ import annotations

import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("morning_paper.py")
SPEC = importlib.util.spec_from_file_location("morning_paper", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
morning_paper = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = morning_paper
SPEC.loader.exec_module(morning_paper)


def write_feed(path: Path) -> None:
    path.write_text(
        '{"items":['
        '{"title":"Passive AI shells","source":"HN","url":"https://example.com/passive","summary":"A local-first agent loop.","tags":["passive-ai","agents"]},'
        '{"title":"CSS layout notes","source":"RSS","summary":"Frontend layout tips.","tags":["frontend"]},'
        '{"title":"Agent memory paper","source":"arXiv","summary":"Long-term memory for coding agents.","tags":["memory","agents"]}'
        ']}'
    )


def test_generate_ranks_feed_items_by_interest_tags(tmp_path: Path) -> None:
    feed_path = tmp_path / "feed.json"
    state_path = tmp_path / "state.json"
    write_feed(feed_path)
    state_path.write_text('{"date":"2026-04-17","interests":["passive-ai","memory"]}')

    paths = morning_paper.generate(feed_path, tmp_path, state_path=state_path)
    text = paths.morning_paper.read_text()

    assert paths.morning_paper == tmp_path / ".mew" / "morning-paper" / "2026-04-17.md"
    assert "# Mew Morning Paper 2026-04-17" in text
    assert "### 1. Agent memory paper" in text
    assert "### 2. Passive AI shells" in text
    assert text.index("### 1. Agent memory paper") < text.index("### 2. Passive AI shells")
    assert "- why: matched tag `memory`" in text
    assert "- why: matched tag `passive-ai`" in text


def test_cli_interests_are_used_without_state(tmp_path: Path) -> None:
    feed_path = tmp_path / "feed.json"
    write_feed(feed_path)

    paths = morning_paper.generate(
        feed_path,
        tmp_path,
        explicit_date="2026-04-17",
        explicit_interests=["frontend"],
        limit=1,
    )
    text = paths.morning_paper.read_text()

    assert "### 1. CSS layout notes" in text
    assert "### 2." not in text
    assert "- frontend" in text


def test_text_mentions_can_match_interests_when_tags_do_not(tmp_path: Path) -> None:
    feed_path = tmp_path / "feed.json"
    feed_path.write_text(
        '{"items":[{"title":"Local-first tools","source":"RSS","summary":"A passive-ai workflow without matching tags.","tags":["tools"]}]}'
    )

    paths = morning_paper.generate(
        feed_path,
        tmp_path,
        explicit_date="2026-04-17",
        explicit_interests=["passive-ai"],
    )
    text = paths.morning_paper.read_text()

    assert "- score: 4" in text
    assert "- why: mentioned `passive-ai`" in text


def test_no_interests_keeps_items_for_exploration(tmp_path: Path) -> None:
    feed_path = tmp_path / "feed.json"
    write_feed(feed_path)

    paths = morning_paper.generate(feed_path, tmp_path, explicit_date="2026-04-17", limit=1)
    text = paths.morning_paper.read_text()

    assert "- No interest tags configured" in text
    assert "- why: No interest tags configured; kept for exploration" in text


def test_empty_feed_renders_fallback(tmp_path: Path) -> None:
    feed_path = tmp_path / "feed.json"
    feed_path.write_text('{"items":[]}')

    paths = morning_paper.generate(feed_path, tmp_path, explicit_date="2026-04-17")
    text = paths.morning_paper.read_text()

    assert "- No feed items recorded" in text


def test_main_prints_created_path(tmp_path: Path) -> None:
    feed_path = tmp_path / "feed.json"
    write_feed(feed_path)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = morning_paper.main(
            [str(feed_path), "--output-dir", str(tmp_path), "--date", "2026-04-17", "--interest", "agents"]
        )

    assert exit_code == 0
    assert stdout.getvalue().strip() == str(tmp_path / ".mew" / "morning-paper" / "2026-04-17.md")
