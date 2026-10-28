"""Same-origin HTTP adapter for the shell application service."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .session import Session, SessionConflictError
from .websocket_events import install_websocket_route

CONFLICT = 409
FORBIDDEN = 403
MAX_COMMAND_LENGTH = 65_536
IDENTIFIER_LIMIT = 128


class SessionRequest(BaseModel):
    """Identify the process whose state a request intends to change."""

    session_id: str


class CommandRequest(SessionRequest):
    """A command with an idempotency key supplied by the client."""

    request_id: str = Field(min_length=1, max_length=IDENTIFIER_LIMIT)
    line: str = Field(max_length=MAX_COMMAND_LENGTH)


class CloseRequest(SessionRequest):
    """Acknowledge the final transcript position."""

    cursor: int = Field(ge=0)


def create_app(session: Session, assets: Path | None = None) -> FastAPI:
    """Create a transport adapter around an already initialized session."""
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Release the execution worker when the host stops."""
        yield
        session.dispose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"],
    )
    install_guards(app)
    install_session_routes(app, session)
    install_command_routes(app, session)
    install_event_route(app, session)
    install_websocket_route(app, session)
    if assets is not None:
        app.mount("/", StaticFiles(directory=assets, html=True))
    return app


def install_guards(app: FastAPI) -> None:
    """Reject cross-origin mutations and convert session conflicts."""
    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        """Keep browser mutations on the launcher's own origin."""
        origin = request.headers.get("origin")
        expected = str(request.base_url).rstrip("/")
        if request.method == "POST" and origin not in {None, expected}:
            return JSONResponse(
                {"detail": "Запрос с другого сайта запрещён."},
                status_code=FORBIDDEN,
            )
        return await call_next(request)

    @app.exception_handler(SessionConflictError)
    async def conflict(request: Request, error: SessionConflictError):
        """Report state conflicts without a server traceback."""
        return JSONResponse({"detail": str(error)}, status_code=CONFLICT)


def install_session_routes(app: FastAPI, session: Session) -> None:
    """Expose snapshots and idempotent lifecycle requests."""
    @app.get("/api/session")
    def snapshot():
        """Return the current projection and its event cursor."""
        return session.snapshot()

    @app.post("/api/session/start")
    def start(body: SessionRequest):
        """Begin once a browser has attached to the event stream."""
        session.validate(body.session_id)
        session.start()
        return {"state": session.state}

    @app.post("/api/session/ack-close")
    def acknowledge(body: CloseRequest):
        """Allow the process to exit after final output is rendered."""
        session.validate(body.session_id)
        session.acknowledge_close(body.cursor)
        return {"acknowledged": True}


def install_command_routes(app: FastAPI, session: Session) -> None:
    """Accept command requests independently of eventual shell results."""
    @app.post("/api/commands", status_code=202)
    def submit(body: CommandRequest):
        """Queue a command with exactly-once handling of its request ID."""
        session.validate(body.session_id)
        identifier = session.submit(body.request_id, body.line)
        return {"id": identifier}


def install_event_route(app: FastAPI, session: Session) -> None:
    """Expose a resumable stream over the same journal as snapshots."""
    def validated_cursor(
        request: Request, session_id: str,
        after: Annotated[int, Query(ge=0)] = 0,
    ) -> int:
        """Validate before the streaming response sends its headers."""
        session.validate(session_id)
        return event_cursor(request, after, session)

    @app.get("/api/events", response_class=EventSourceResponse)
    async def events(cursor: Annotated[int, Depends(validated_cursor)]):
        """Resume from an explicit or browser-provided event cursor."""
        async for event in stream_events(session, cursor):
            yield event


def event_cursor(request: Request, after: int, session: Session) -> int:
    """Validate a reconnect cursor before opening a streaming response."""
    try:
        cursor = int(request.headers.get("last-event-id", after))
    except ValueError as error:
        raise HTTPException(CONFLICT, "Неверный курсор событий.") from error
    if not 0 <= cursor <= session.snapshot()["cursor"]:
        raise HTTPException(CONFLICT, "Неверный курсор событий.")
    return cursor


async def stream_events(session: Session, cursor: int):
    """Replay and then follow the journal without gaps between phases."""
    while True:
        batch = await asyncio.to_thread(session.journal.after, cursor)
        for event in batch:
            cursor = event["seq"]
            yield ServerSentEvent(data=event, id=str(cursor))
        if session.state == "closed" and not batch:
            return
