"""Replayable browser events without occupying HTTP connection slots."""

import asyncio
from collections.abc import Awaitable

import anyio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .session import Session, SessionConflictError

POLICY_VIOLATION = 1008
NORMAL_CLOSURE = 1000


def connection_cursor(socket: WebSocket, session: Session) -> int:
    """Validate browser origin, session identity, and the replay position."""
    scheme = "https" if socket.url.scheme == "wss" else "http"
    expected = f"{scheme}://{socket.url.netloc}"
    if socket.headers.get("origin") not in {None, expected}:
        raise SessionConflictError("Недопустимый источник подключения.")
    session.validate(socket.query_params.get("session_id", ""))
    try:
        cursor = int(socket.query_params.get("after", "0"))
    except ValueError as error:
        raise SessionConflictError("Неверный курсор событий.") from error
    with session.journal.condition:
        if not 0 <= cursor <= len(session.journal.events):
            raise SessionConflictError("Неверный курсор событий.")
    return cursor


async def send_events(socket: WebSocket, session: Session, cursor: int) -> None:
    """Replay and follow journal events until the final state is delivered."""
    while True:
        batch = await asyncio.to_thread(session.journal.after, cursor)
        for event in batch:
            await socket.send_json(event)
            cursor = event["seq"]
        with session.journal.condition:
            finished = (
                session.state == "closed"
                and cursor == len(session.journal.events)
            )
        if finished:
            await socket.close(code=NORMAL_CLOSURE)
            return


async def receive_disconnect(socket: WebSocket) -> None:
    """Notice an idle peer leaving even when no new events are emitted."""
    while True:
        message = await socket.receive()
        if message["type"] == "websocket.disconnect":
            return


async def follow_connection(
    socket: WebSocket, session: Session, cursor: int,
) -> None:
    """Cancel and join both halves when the peer or sender finishes."""
    async with anyio.create_task_group() as group:
        group.start_soon(
            finish_together, send_events(socket, session, cursor),
            group.cancel_scope,
        )
        group.start_soon(
            finish_together, receive_disconnect(socket), group.cancel_scope,
        )


async def finish_together(
    operation: Awaitable[None], scope: anyio.CancelScope,
) -> None:
    """Cancel the connection task group when either operation ends."""
    try:
        await operation
    except WebSocketDisconnect:
        pass
    finally:
        scope.cancel()


def install_websocket_route(app: FastAPI, session: Session) -> None:
    """Register an event-only WebSocket; mutations remain HTTP requests."""
    @app.websocket("/api/events/ws")
    async def events(socket: WebSocket):
        """Accept a browser connection and enforce policy before any data."""
        await socket.accept()
        try:
            cursor = connection_cursor(socket, session)
        except SessionConflictError as error:
            await socket.close(code=POLICY_VIOLATION, reason=str(error))
            return
        await follow_connection(socket, session, cursor)
