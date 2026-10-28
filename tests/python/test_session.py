"""Application invariants independent of HTTP and browser frameworks."""

import pytest

from shell_emulator.engine import Shell
from shell_emulator.session import Session, SessionConflictError
from shell_emulator.vfs import Node

WAIT_SECONDS = 3


@pytest.fixture
def session():
    """Dispose each isolated worker even when an assertion fails."""
    instance = Session(Shell({"HOME": "/virtual/home"}))
    yield instance
    instance.dispose()


def wait_for_commands(session, count):
    """Wait for completed results through the journal condition."""
    with session.journal.condition:
        ready = session.journal.condition.wait_for(
            lambda: sum(
                event["kind"] == "complete"
                for event in session.journal.events
            ) >= count,
            timeout=WAIT_SECONDS,
        )
    assert ready, "execution worker did not finish"


def test_commands_execute_in_acceptance_order(session):
    """Relative state changes cannot overtake earlier accepted commands."""
    session.shell.vfs.nodes["/first"] = Node("dir", 0o755)
    session.shell.vfs.nodes["/first/second"] = Node("dir", 0o755)
    session.start()
    lines = ["cd first", "cd second", "cd ..", "cd ..", "cd -"]
    for index, line in enumerate(lines):
        session.submit(str(index), line)
    wait_for_commands(session, len(lines))
    inputs = [e["line"] for e in session.journal.events if e["kind"] == "input"]
    assert inputs == lines
    assert session.shell.cwd == "/first"
    assert session.snapshot()["cwd"] == "/first"


def test_uncertain_acknowledgment_does_not_repeat_command(session):
    """The same request identifier is safe before and after completion."""
    session.start()
    session.submit("repeat", "ls")
    session.submit("repeat", "ls")
    wait_for_commands(session, 1)
    session.submit("repeat", "ls")
    inputs = [e for e in session.journal.events if e["kind"] == "input"]
    assert len(inputs) == 1
    with pytest.raises(SessionConflictError):
        session.submit("repeat", "cd")


def test_start_and_snapshot_preserve_existing_session(session):
    """A browser refresh is a read plus an idempotent handshake."""
    session.start()
    session.submit("first", "ls")
    wait_for_commands(session, 1)
    before = session.snapshot()
    session.start()
    assert session.snapshot() == before


def test_events_between_snapshot_and_subscription_are_replayed(session):
    """The journal closes the snapshot-to-stream race."""
    snapshot = session.snapshot()
    session.start()
    session.submit("gap", "ls")
    wait_for_commands(session, 1)
    batch = session.journal.after(snapshot["cursor"])
    assert batch == session.snapshot()["events"]
    assert [e["seq"] for e in batch] == list(range(1, len(batch) + 1))


def test_exit_waits_for_render_acknowledgment(session):
    """The process gets time to deliver the final transcript."""
    session.start()
    session.submit("end", "exit")
    wait_for_commands(session, 1)
    assert session.state == "closed"
    assert not session.shutdown_requested.is_set()
    with pytest.raises(SessionConflictError):
        session.acknowledge_close(0)
    session.acknowledge_close(session.snapshot()["cursor"])
    assert session.shutdown_requested.is_set()
    with pytest.raises(SessionConflictError):
        session.submit("late", "ls")


def test_stale_and_premature_requests_are_rejected(session):
    """Fresh processes cannot receive commands from stale browser tabs."""
    with pytest.raises(SessionConflictError):
        session.validate("earlier-launch")
    with pytest.raises(SessionConflictError):
        session.submit("early", "ls")


def test_shell_error_does_not_break_executor(session):
    """A command error is output; the next accepted command still runs."""
    session.start()
    session.submit("bad", "not-a-command")
    session.submit("good", "ls")
    wait_for_commands(session, 2)
    statuses = [
        e["status"] for e in session.journal.events if e["kind"] == "complete"
    ]
    assert statuses == [127, 0]
