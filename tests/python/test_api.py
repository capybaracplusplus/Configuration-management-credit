"""HTTP boundary validation and session lifecycle integration."""

import getpass
import socket

import pytest
from fastapi.testclient import TestClient

from shell_emulator.api import create_app
from shell_emulator.session import Session


@pytest.fixture
def client():
    """Run application lifespan around each isolated HTTP test."""
    with TestClient(
        create_app(Session()), base_url="http://127.0.0.1",
    ) as connection:
        yield connection


def test_real_identity_and_ready_handshake(client):
    """Browser title data is sourced from the host operating system."""
    snapshot = client.get("/api/session").json()
    assert snapshot["username"] == getpass.getuser()
    assert snapshot["hostname"] == socket.gethostname()
    body = {"session_id": snapshot["session_id"]}
    response = client.post("/api/session/start", json=body)
    assert response.json()["state"] == "ready"
    assert client.post("/api/session/start", json=body).status_code == 200


def test_commands_validate_session_and_payload(client):
    """Malformed requests do not reach the command engine."""
    assert client.post("/api/commands", json={}).status_code == 422
    response = client.post("/api/commands", json={
        "session_id": "stale", "request_id": "x", "line": "ls",
    })
    assert response.status_code == 409


def test_cross_origin_mutation_is_rejected(client):
    """An unrelated browser origin cannot control the local shell."""
    response = client.post(
        "/api/session/start", json={"session_id": "unused"},
        headers={"Origin": "https://unrelated.example"},
    )
    assert response.status_code == 403


def test_invalid_event_cursor_fails_before_streaming(client):
    """A nonexistent journal position is a conflict, not a silent gap."""
    identifier = client.get("/api/session").json()["session_id"]
    response = client.get(
        "/api/events", params={"session_id": identifier, "after": 100},
    )
    assert response.status_code == 409
