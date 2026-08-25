from pathlib import Path

import pytest

from ecommerce_etl.migrations import discover_migrations


def test_discover_migrations_sorts_by_version(tmp_path: Path) -> None:
    (tmp_path / "002_second.sql").write_text("SELECT 2;", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")

    assert [path.name for path in discover_migrations(tmp_path)] == [
        "001_first.sql",
        "002_second.sql",
    ]


def test_discover_migrations_rejects_duplicate_versions(tmp_path: Path) -> None:
    (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "001_duplicate.sql").write_text("SELECT 2;", encoding="utf-8")

    with pytest.raises(ValueError, match="versions must be unique"):
        discover_migrations(tmp_path)
