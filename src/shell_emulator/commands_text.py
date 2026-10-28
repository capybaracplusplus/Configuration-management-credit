"""Текстовые команды, работающие только с аргументами и памятью VFS."""

from dataclasses import dataclass
from itertools import groupby
from typing import TYPE_CHECKING

from .errors import ArgumentError, ShellError
from .models import CommandResult

if TYPE_CHECKING:
    from .engine import Shell

ONE_OPERAND = 1
SINGLE_OCCURRENCE = 1
MIN_REPEATED_COUNT = 2
COUNT_WIDTH = 7


@dataclass(frozen=True, slots=True)
class UniqOptions:
    """Проверенные режимы фильтрации соседних одинаковых строк."""

    path: str
    counts: bool = False
    repeated: bool = False
    unique: bool = False


def echo(shell: "Shell", args: list[str]) -> CommandResult:
    """Вывести аргументы без интерпретации управляющих последовательностей."""
    index = 0
    newline = "\n"
    while index < len(args) and args[index] == "-n":
        newline = ""
        index += 1
    if index < len(args) and args[index] == "--":
        index += 1
    return CommandResult(stdout=" ".join(args[index:]) + newline)


def uniq_options(args: list[str]) -> UniqOptions:
    """Прочитать объединённые флаги и единственный путь входного файла."""
    flags: set[str] = set()
    paths = []
    scanning_options = True
    for argument in args:
        if scanning_options and argument == "--":
            scanning_options = False
        elif scanning_options and argument.startswith("-") and argument != "-":
            current = set(argument[1:])
            if not current.issubset({"c", "d", "u"}):
                raise ArgumentError(f"uniq: неизвестный параметр {argument}")
            flags.update(current)
        else:
            paths.append(argument)
            scanning_options = False
    if len(paths) != ONE_OPERAND:
        raise ArgumentError("uniq: требуется ровно один путь к файлу")
    if {"d", "u"}.issubset(flags):
        raise ArgumentError("uniq: параметры -d и -u несовместимы")
    return UniqOptions(paths[0], "c" in flags, "d" in flags, "u" in flags)


def line_groups(text: str) -> list[tuple[str, int]]:
    """Сгруппировать соседние строки, считая разделителем только LF."""
    if not text:
        return []
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()
    return [(line, sum(1 for _ in group)) for line, group in groupby(lines)]


def select_groups(text: str, options: UniqOptions) -> str:
    """Отфильтровать группы, сохранив отсутствие последнего перевода строки."""
    groups = line_groups(text)
    output = []
    for index, (line, count) in enumerate(groups):
        if options.repeated and count < MIN_REPEATED_COUNT:
            continue
        if options.unique and count != SINGLE_OCCURRENCE:
            continue
        prefix = f"{count:{COUNT_WIDTH}d} " if options.counts else ""
        final_group = index == len(groups) - SINGLE_OCCURRENCE
        newline = "" if final_group and not text.endswith("\n") else "\n"
        output.append(f"{prefix}{line}{newline}")
    return "".join(output)


def uniq(shell: "Shell", args: list[str]) -> CommandResult:
    """Убрать либо посчитать только соседние дубликаты строк UTF-8 файла."""
    options = uniq_options(args)
    data = shell.vfs.read_file(options.path, shell.cwd)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ShellError(
            f"uniq: файл не является UTF-8: {options.path}",
        ) from error
    return CommandResult(stdout=select_groups(text, options))
