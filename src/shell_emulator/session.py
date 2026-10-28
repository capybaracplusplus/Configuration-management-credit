"""Application service owning one shell and its ordered execution queue."""

import getpass
import logging
import socket
from dataclasses import dataclass
from queue import Queue
from threading import Event, Thread, Timer
from typing import Any
from uuid import uuid4

from .configuration import ScriptLine
from .engine import Shell
from .journal import Journal
from .models import CommandResult

SHUTDOWN_GRACE_SECONDS = 5.0
WORKER_JOIN_SECONDS = 2.0


class SessionConflictError(Exception):
    """A request cannot be applied to the current session state."""


@dataclass(frozen=True)
class CommandJob:
    """An accepted command with a stable request identity."""

    identifier: str
    line: str
    source: str | None = None
    number: int | None = None


@dataclass(frozen=True)
class StartupJob:
    """A startup script reserved ahead of interactive commands."""

    lines: tuple[ScriptLine, ...]


class Session:
    """Serialize commands and publish their observable effects."""

    def __init__(
        self, shell: Shell | None = None,
        configuration: dict[str, str | None] | None = None,
        startup: list[ScriptLine] | None = None,
    ) -> None:
        """Initialize state without starting a browser or script."""
        self.shell = shell or Shell()
        self.identifier = str(uuid4())
        self.username = getpass.getuser()
        self.hostname = socket.gethostname()
        self.title = f"Эмулятор - [{self.username}@{self.hostname}]"
        self.journal = Journal()
        self.state = "waiting"
        self.cwd = self.shell.cwd
        self.configuration: dict[str, str | None] = configuration or {
            "vfs": None, "startup_script": None,
        }
        self._startup = tuple(startup or ())
        self.shutdown_requested = Event()
        self._requests: dict[str, str] = {}
        self._jobs: Queue[CommandJob | StartupJob | None] = Queue()
        self._timer: Timer | None = None
        self._worker = Thread(target=self._work, daemon=True)
        self._worker.start()

    def validate(self, identifier: str) -> None:
        """Reject requests belonging to a different process launch."""
        if identifier != self.identifier:
            raise SessionConflictError("Сеанс изменился: обновите страницу.")

    def snapshot(self) -> dict[str, Any]:
        """Read metadata and its exact transcript cursor atomically."""
        with self.journal.condition:
            return {
                "session_id": self.identifier,
                "username": self.username,
                "hostname": self.hostname,
                "title": self.title,
                "cwd": self.cwd,
                "state": self.state,
                "configuration": dict(self.configuration),
                "events": list(self.journal.events),
                "cursor": len(self.journal.events),
            }

    def start(self) -> None:
        """Make the session ready once the browser is listening."""
        with self.journal.condition:
            if self.state == "waiting":
                self._show_configuration()
                if self._startup:
                    self._transition("starting")
                    self._jobs.put(StartupJob(self._startup))
                else:
                    self._transition("ready")

    def _show_configuration(self) -> None:
        """Expose the selected physical paths in the visible dialogue."""
        values = self.configuration
        text = (
            f"VFS: {values['vfs'] or 'не задан'}\n"
            f"Стартовый скрипт: {values['startup_script'] or 'не задан'}\n"
        )
        self.journal.append("output", stream="stdout", text=text)
        self._show_vfs()

    def _show_vfs(self) -> None:
        """Make the loaded archive structure observable before commands."""
        nodes = self.shell.vfs.nodes
        files = sum(node.kind == "file" for node in nodes.values())
        directories = len(nodes) - files
        children = sorted(
            path.removeprefix("/") for path in nodes
            if path != "/" and "/" not in path.removeprefix("/")
        )
        roots = ", ".join(children) or "пусто"
        text = (
            f"VFS загружена в память: файлов {files}, "
            f"каталогов (с корнем) {directories}.\n"
            f"Корень VFS: {roots}\n"
        )
        self.journal.append("output", stream="stdout", text=text)

    def submit(self, identifier: str, line: str) -> str:
        """Accept a command exactly once and preserve acceptance order."""
        with self.journal.condition:
            if identifier in self._requests:
                if self._requests[identifier] != line:
                    raise SessionConflictError(
                        "Идентификатор команды уже занят.",
                    )
                return identifier
            if self.state not in {"ready", "running"}:
                raise SessionConflictError("Сеанс не принимает команды.")
            self._requests[identifier] = line
            self._jobs.put(CommandJob(identifier, line))
            return identifier

    def acknowledge_close(self, cursor: int) -> None:
        """Allow shutdown only after the last event was rendered."""
        with self.journal.condition:
            if self.state != "closed":
                raise SessionConflictError("Сеанс ещё не завершён.")
            if cursor < len(self.journal.events):
                raise SessionConflictError("Получен не весь вывод сеанса.")
            self.shutdown_requested.set()

    def dispose(self) -> None:
        """Stop background resources when the HTTP host shuts down."""
        if self._timer is not None:
            self._timer.cancel()
        self._jobs.put(None)
        self._worker.join(WORKER_JOIN_SECONDS)

    def _transition(self, state: str) -> None:
        """Record a lifecycle transition under the journal lock."""
        self.state = state
        self.journal.append("state", state=state, cwd=self.cwd)

    def _work(self) -> None:
        """Execute accepted commands on a single dedicated worker."""
        while (job := self._jobs.get()) is not None:
            if self.state == "closed":
                continue
            if isinstance(job, StartupJob):
                self._run_startup(job)
            else:
                self._execute(job)

    def _run_startup(self, job: StartupJob) -> None:
        """Execute a script once and stop immediately on its exit command."""
        for line in job.lines:
            if self.state == "closed":
                return
            command = CommandJob(
                f"startup:{line.number}", line.text, line.source, line.number,
            )
            self._execute(command, starting=True)
        with self.journal.condition:
            if self.state != "closed":
                self._transition("ready")

    def _execute(self, job: CommandJob, starting: bool = False) -> None:
        """Publish input, domain results, and the next lifecycle state."""
        with self.journal.condition:
            if not starting:
                self._transition("running")
            prompt = f"{self.username}@{self.hostname}:{self.cwd}$ "
            self.journal.append(
                "input", command_id=job.identifier,
                line=job.line, prompt=prompt,
            )
        result = self._evaluate(job.line)
        with self.journal.condition:
            self.cwd = self.shell.cwd
            self._publish_result(job, result)
            self.journal.append(
                "complete", command_id=job.identifier,
                status=result.status, cwd=self.cwd,
            )
            if result.exit_requested:
                self._close()
            elif not starting:
                self._transition("ready")

    def _publish_result(self, job: CommandJob, result: CommandResult) -> None:
        """Attach script locations to diagnostics without altering stdout."""
        for stream in ("stdout", "stderr"):
            text = getattr(result, stream)
            if text:
                if stream == "stderr" and job.source is not None:
                    text = f"{job.source}:{job.number}: {text}"
                self.journal.append(
                    "output", command_id=job.identifier,
                    stream=stream, text=text,
                )

    def _evaluate(self, line: str) -> CommandResult:
        """Keep an unexpected handler failure from killing the executor."""
        try:
            return self.shell.execute(line)
        except Exception:
            logging.getLogger(__name__).exception("Command handler failed")
            return CommandResult(
                stderr="Внутренняя ошибка выполнения команды.\n", status=1,
            )

    def _close(self) -> None:
        """Give the browser a bounded opportunity to render final output."""
        self._transition("closing")
        self._transition("closed")
        self._timer = Timer(
            SHUTDOWN_GRACE_SECONDS, self.shutdown_requested.set,
        )
        self._timer.daemon = True
        self._timer.start()
