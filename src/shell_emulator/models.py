"""Значения, которыми обмениваются оболочка и прикладной слой."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Вывод, код завершения и запрос остановки одной команды."""

    stdout: str = ""
    stderr: str = ""
    status: int = 0
    exit_requested: bool = False
