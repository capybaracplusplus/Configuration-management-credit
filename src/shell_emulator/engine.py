"""Командный движок, независимый от интерфейса и HTTP."""

import os
from collections.abc import Mapping

from .commands_calendar import cal
from .commands_copy import copy
from .commands_navigation import change_directory, list_entries
from .commands_permissions import chmod
from .commands_text import echo, uniq
from .errors import ArgumentError, ShellError, UnknownCommandError
from .models import CommandResult
from .parser import parse_command
from .vfs import VirtualFS


class Shell:
    """Сеанс оболочки с собственным снимком окружения процесса."""

    def __init__(
        self, environment: Mapping[str, str] | None = None,
        vfs: VirtualFS | None = None,
    ):
        """Создать сеанс в корне виртуальной файловой системы."""
        source = os.environ if environment is None else environment
        self.environment = dict(source)
        self.cwd = "/"
        self.previous_cwd: str | None = None
        self.vfs = VirtualFS() if vfs is None else vfs

    def execute(self, line: str) -> CommandResult:
        """Разобрать строку и преобразовать ошибки в результат команды."""
        try:
            words = parse_command(line, self.environment)
            if not words:
                return CommandResult()
            return self._dispatch(words[0], words[1:])
        except ShellError as error:
            return CommandResult(stderr=f"{error}\n", status=error.status)

    def _dispatch(self, command: str, arguments: list[str]) -> CommandResult:
        """Выбрать доменный обработчик либо завершить сеанс."""
        if command == "exit":
            if arguments:
                raise ArgumentError("exit: аргументы не поддерживаются")
            return CommandResult(exit_requested=True)
        handlers = {
            "ls": list_entries,
            "cd": change_directory,
            "echo": echo,
            "uniq": uniq,
            "cal": cal,
            "cp": copy,
            "chmod": chmod,
        }
        handler = handlers.get(command)
        if handler is None:
            raise UnknownCommandError(f"Неизвестная команда: {command}")
        return handler(self, arguments)
