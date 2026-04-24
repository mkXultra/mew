from pathlib import Path

from mew.report_io import backup_path, write_generated_report


def test_write_generated_report_backs_up_changed_existing_file(tmp_path: Path) -> None:
    path = tmp_path / ".mew" / "journal" / "2026-04-17.md"
    path.parent.mkdir(parents=True)
    path.write_text("human edit\n", encoding="utf-8")

    write_generated_report(path, "generated\n")

    assert path.read_text(encoding="utf-8") == "generated\n"
    assert backup_path(path).read_text(encoding="utf-8") == "human edit\n"


def test_write_generated_report_skips_backup_when_content_is_same(tmp_path: Path) -> None:
    path = tmp_path / ".mew" / "journal" / "2026-04-17.md"

    write_generated_report(path, "generated\n")
    write_generated_report(path, "generated\n")

    assert not backup_path(path).exists()


def test_write_generated_report_keeps_existing_backup(tmp_path: Path) -> None:
    path = tmp_path / ".mew" / "journal" / "2026-04-17.md"
    path.parent.mkdir(parents=True)
    path.write_text("second human edit\n", encoding="utf-8")
    backup_path(path).write_text("first human edit\n", encoding="utf-8")

    write_generated_report(path, "generated\n")

    assert path.read_text(encoding="utf-8") == "generated\n"
    assert backup_path(path).read_text(encoding="utf-8") == "first human edit\n"
