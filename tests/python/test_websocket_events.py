"""Live journal replay, browser policy, and idle disconnect cleanup."""

import asyncio
from threading import Event

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from shell_emulator import websocket_events
from shell_emulator.api import create_app
from shell_emulator.session import Session

BASE = "ws://127.0.0.1/api/events/ws"
WAIT_SECONDS = 2


@pytest.fixture
def client_session():
    """Keep one authoritative session behind HTTP and WebSocket adapters."""
    session = Session()
    with TestClient(create_app(session), base_url="http://127.0.0.1") as client:
        yield client, session


def endpoint(session, after=0):
    """Build a connection URL with an explicit replay cursor."""
    return f"{BASE}?session_id={session.identifier}&after={after}"


def test_connection_is_ready_before_startup_produces_events(client_session):
    """The browser handshake does not depend on receiving the first event."""
    client, session = client_session
    with client.websocket_connect(endpoint(session)) as socket:
        response = client.post("/api/session/start", json={
            "session_id": session.identifier,
        })
        assert response.status_code == 200
        events = [socket.receive_json() for _ in range(3)]
    assert [event["seq"] for event in events] == [1, 2, 3]
    assert events[-1]["state"] == "ready"


def test_replay_then_new_commands_share_one_ordered_stream(client_session):
    """Events between snapshot and connection are replayed without a gap."""
    client, session = client_session
    session.start()
    with client.websocket_connect(endpoint(session, after=1)) as socket:
        assert socket.receive_json()["seq"] == 2
        assert socket.receive_json()["seq"] == 3
        response = client.post("/api/commands", json={
            "session_id": session.identifier,
            "request_id": "ws-command", "line": "echo socket",
        })
        assert response.status_code == 202
        events = [socket.receive_json() for _ in range(5)]
    assert [event["seq"] for event in events] == [4, 5, 6, 7, 8]
    assert events[2]["text"] == "socket\n"


@pytest.mark.parametrize("origin", [None, "http://127.0.0.1"])
def test_same_origin_and_nonbrowser_probes_are_allowed(client_session, origin):
    """Browser requests are same-origin; API probes may omit Origin."""
    client, session = client_session
    session.start()
    headers = {} if origin is None else {"origin": origin}
    with client.websocket_connect(endpoint(session), headers=headers) as socket:
        assert socket.receive_json()["seq"] == 1


@pytest.mark.parametrize("origin", ["https://unrelated.example", "null"])
def test_cross_origin_socket_closes_without_journal_data(
    client_session, origin,
):
    """An unrelated page cannot read events from the local emulator."""
    client, session = client_session
    session.start()
    with client.websocket_connect(
        endpoint(session), headers={"origin": origin},
    ) as socket:
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
    assert error.value.code == 1008


@pytest.mark.parametrize("cursor", ["-1", "invalid", "100"])
def test_invalid_cursor_closes_with_policy_violation(client_session, cursor):
    """Invalid cursors cannot silently lose or duplicate transcript events."""
    client, session = client_session
    with client.websocket_connect(endpoint(session, cursor)) as socket:
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
    assert error.value.code == 1008


def test_stale_session_closes_with_policy_violation(client_session):
    """A reconnect from a previous launcher cannot observe the new session."""
    client, _ = client_session
    with client.websocket_connect(f"{BASE}?session_id=stale") as socket:
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
    assert error.value.code == 1008


def test_idle_disconnect_cancels_and_joins_journal_sender(
    client_session, monkeypatch,
):
    """An idle closed browser does not leave a background stream alive."""
    client, session = client_session
    stopped = Event()

    async def wait_forever(socket, current_session, cursor):
        """Observe cancellation without requiring another journal event."""
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(websocket_events, "send_events", wait_forever)
    with client.websocket_connect(endpoint(session)):
        pass
    assert stopped.wait(WAIT_SECONDS)


def test_exit_delivers_final_state_and_allows_http_ack(client_session):
    """Normal socket closure follows the final transcript; HTTP stays usable."""
    client, session = client_session
    session.start()
    cursor = session.snapshot()["cursor"]
    with client.websocket_connect(endpoint(session, cursor)) as socket:
        session.submit("exit", "exit")
        events = [socket.receive_json() for _ in range(5)]
        assert events[-1]["state"] == "closed"
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
    assert error.value.code == 1000
    response = client.post("/api/session/ack-close", json={
        "session_id": session.identifier, "cursor": events[-1]["seq"],
    })
    assert response.status_code == 200
    assert session.shutdown_requested.is_set()
