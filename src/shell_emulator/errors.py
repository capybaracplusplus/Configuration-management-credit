"""Ошибки предметной области без зависимости от транспорта."""


class ShellError(Exception):
    """Понятная пользователю ошибка исполнения команды."""

    status = 1


class ParseError(ShellError):
    """Ошибка разбора строки оболочки."""

    status = 2


class ArgumentError(ShellError):
    """Неверные аргументы известной команды."""

    status = 2


class UnknownCommandError(ShellError):
    """Имя команды отсутствует в наборе эмулятора."""

    status = 127
