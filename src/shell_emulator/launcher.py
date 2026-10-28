"""Local HTTP process and browser lifecycle."""

import asyncio
import socket
import webbrowser
from pathlib import Path

import uvicorn

from .api import create_app
from .session import Session

LOOPBACK = "127.0.0.1"
AUTOMATIC_PORT = 0
WATCH_INTERVAL = 0.05
GRACEFUL_TIMEOUT = 2
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def launch(session: Session, open_browser: bool = True) -> None:
    """Reserve a local port and run one application instance."""
    assets = PROJECT_ROOT / "dist"
    if not (assets / "index.html").is_file():
        session.dispose()
        raise ValueError("Интерфейс не собран. Выполните make build.")
    with socket.socket() as listener:
        listener.bind((LOOPBACK, AUTOMATIC_PORT))
        address, port = listener.getsockname()
        url = f"http://{address}:{port}"
        config = uvicorn.Config(
            create_app(session, assets), host=address, port=port,
            log_level="warning", timeout_graceful_shutdown=GRACEFUL_TIMEOUT,
        )
        server = uvicorn.Server(config)
        asyncio.run(serve(server, listener, session, url, open_browser))


async def serve(server, listener, session, url, open_browser):
    """Keep startup and shutdown observers attached to the HTTP host."""
    observer = asyncio.create_task(observe(server, session, url, open_browser))
    try:
        await server.serve(sockets=[listener])
    finally:
        observer.cancel()
        await asyncio.gather(observer, return_exceptions=True)


async def observe(server, session, url, open_browser):
    """Open the browser only after readiness and honor shell shutdown."""
    while not server.started:
        await asyncio.sleep(WATCH_INTERVAL)
    print(f"Эмулятор: {url}", flush=True)
    if open_browser:
        await asyncio.to_thread(webbrowser.open, url)
    while not session.shutdown_requested.is_set():
        await asyncio.sleep(WATCH_INTERVAL)
    server.should_exit = True
