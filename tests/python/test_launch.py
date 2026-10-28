"""Physical configuration loading before a browser session is created."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from shell_emulator import __main__ as entry


@pytest.mark.parametrize("invalid", ["missing.zip", "invalid.zip"])
def test_invalid_vfs_reports_failure_before_browser(
    tmp_path, monkeypatch, capsys, invalid,
):
    """A bad archive is a visible launch failure with a nonzero status."""
    path = tmp_path / invalid
    if invalid == "invalid.zip":
        path.write_text("not an archive")
    monkeypatch.setattr("sys.argv", ["emulator", "--vfs", str(path)])
    monkeypatch.setattr(entry, "launch", lambda _: pytest.fail("opened GUI"))
    assert entry.main() == 1
    output = capsys.readouterr()
    assert str(path) in output.out
    assert str(path) in output.err


def test_loaded_archive_reaches_session_without_extraction(
    tmp_path, monkeypatch, capsys,
):
    """The startup service receives a populated, memory-only filesystem."""
    archive = tmp_path / "with spaces.zip"
    with ZipFile(archive, "w") as output:
        output.writestr("a/b/c/data.txt", "hello")
    before = archive.read_bytes()
    monkeypatch.setattr("sys.argv", ["emulator", "--vfs", str(archive)])
    sessions = []
    monkeypatch.setattr(entry, "launch", sessions.append)
    try:
        assert entry.main() == 0
        session = sessions[0]
        assert session.shell.vfs.read_file("/a/b/c/data.txt") == b"hello"
        session.start()
        text = "".join(e.get("text", "") for e in session.journal.events)
        assert "файлов 1" in text
        assert archive.read_bytes() == before
        assert list(tmp_path.iterdir()) == [archive]
        assert str(Path(archive)) in capsys.readouterr().out
    finally:
        for session in sessions:
            session.dispose()
