"""Mutation persistence, retry behavior, and archive isolation."""

from pathlib import Path

from shell_emulator.engine import Shell
from shell_emulator.session import Session
from shell_emulator.vfs_zip import load_zip
from tools.generate_fixtures import generate

WAIT_SECONDS = 3
MANIFEST = Path(__file__).resolve().parents[2] / "fixtures" / "deep.json"


def finish(session, count):
    """Wait for domain effects and their corresponding journal entries."""
    with session.journal.condition:
        assert session.journal.condition.wait_for(
            lambda: sum(
                event["kind"] == "complete"
                for event in session.journal.events
            ) >= count,
            timeout=WAIT_SECONDS,
        )


def test_retry_and_browser_handshake_preserve_mutated_state(tmp_path):
    """A repeated request and refresh never repeat a copy or startup."""
    archive = tmp_path / "source.zip"
    generate(MANIFEST, archive, "/home/student")
    original = archive.read_bytes()
    session = Session(Shell({}, vfs=load_zip(archive)))
    try:
        session.start()
        line = "cp /assets/payload.bin /copy.bin"
        session.submit("copy", line)
        session.submit("mode", "chmod 000 /copy.bin")
        finish(session, 2)
        session.submit("copy", line)
        before = session.snapshot()
        session.start()
        assert session.snapshot() == before
        node = session.shell.vfs.nodes["/copy.bin"]
        assert node.mode == 0
        assert node.data == bytes([0, 255, 128, 1, 2, 3, 10])
        assert archive.read_bytes() == original
        assert list(tmp_path.iterdir()) == [archive]
        assert "/copy.bin" not in load_zip(archive).nodes
    finally:
        session.dispose()


def test_new_launch_restores_original_permissions_and_contents(tmp_path):
    """Neither permission changes nor recursive copies survive a restart."""
    archive = tmp_path / "source.zip"
    generate(MANIFEST, archive, "/home/student")
    before = archive.read_bytes()
    first = Shell({}, vfs=load_zip(archive))
    assert first.execute("cp -r /tree /copy").status == 0
    assert first.execute("chmod -R 000 /copy").status == 0
    assert first.execute("chmod 000 /docs/repeated.txt").status == 0
    assert first.execute("uniq /docs/repeated.txt").status == 1
    assert all(
        node.mode == 0 for path, node in first.vfs.nodes.items()
        if path == "/copy" or path.startswith("/copy/")
    )
    second = Shell({}, vfs=load_zip(archive))
    assert "/copy" not in second.vfs.nodes
    assert second.vfs.get("/docs/repeated.txt").mode == 0o644
    assert second.execute("uniq /docs/repeated.txt").status == 0
    assert archive.read_bytes() == before
