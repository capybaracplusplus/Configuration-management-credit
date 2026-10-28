"""Startup ordering, error attribution, and exactly-once execution."""

from shell_emulator.configuration import ScriptLine
from shell_emulator.session import Session

WAIT_SECONDS = 3


def finish_startup(session):
    """Wait until the single startup reservation has finished."""
    with session.journal.condition:
        assert session.journal.condition.wait_for(
            lambda: session.state in {"ready", "closed"},
            timeout=WAIT_SECONDS,
        )


def test_errors_keep_original_line_numbers_and_continue():
    """A failed line is shown with its physical script location."""
    lines = [
        ScriptLine(2, "unknown", "demo.emu"),
        ScriptLine(4, 'ls "unterminated', "demo.emu"),
        ScriptLine(5, "echo after", "demo.emu"),
    ]
    session = Session(startup=lines)
    try:
        session.start()
        finish_startup(session)
        output = "".join(e.get("text", "") for e in session.journal.events)
        assert "demo.emu:2:" in output
        assert "demo.emu:4:" in output
        assert "after\n" in output
        before = session.snapshot()
        session.start()
        assert session.snapshot() == before
    finally:
        session.dispose()


def test_script_exit_stops_remaining_commands():
    """Startup exit produces a complete visible journal before shutdown."""
    lines = [
        ScriptLine(1, "ls before", "exit.emu"),
        ScriptLine(2, "exit", "exit.emu"),
        ScriptLine(3, "ls never", "exit.emu"),
    ]
    session = Session(startup=lines)
    try:
        session.start()
        finish_startup(session)
        inputs = [
            e["line"] for e in session.journal.events if e["kind"] == "input"
        ]
        assert inputs == ["ls before", "exit"]
        assert session.state == "closed"
        assert not session.shutdown_requested.is_set()
    finally:
        session.dispose()
