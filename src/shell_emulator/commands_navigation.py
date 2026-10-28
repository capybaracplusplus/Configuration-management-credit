"""Просмотр VFS и изменение рабочего каталога сеанса."""

import stat
from posixpath import basename, dirname
from typing import TYPE_CHECKING

from .errors import ArgumentError
from .models import CommandResult
from .vfs import SEARCH, Node, VfsError

if TYPE_CHECKING:
    from .engine import Shell


def listing_arguments(arguments: list[str]) -> tuple[set[str], list[str]]:
    """Разобрать короткие флаги ls и разделитель параметров."""
    flags: set[str] = set()
    paths: list[str] = []
    options = True
    for argument in arguments:
        if options and argument == "--":
            options = False
        elif options and argument.startswith("-") and argument != "-":
            selected = set(argument[1:])
            if not selected.issubset({"a", "l"}):
                raise ArgumentError(f"ls: неизвестный параметр {argument}")
            flags.update(selected)
        else:
            paths.append(argument)
    return flags, paths or ["."]


def list_entries(shell: "Shell", arguments: list[str]) -> CommandResult:
    """Перечислить операнды независимо, сохраняя успешный вывод при ошибке."""
    flags, paths = listing_arguments(arguments)
    output: list[str] = []
    errors: list[str] = []
    multiple = len(paths) > 1
    for path in paths:
        try:
            output.append(listing(shell, path, flags, multiple))
        except VfsError as error:
            errors.append(f"ls: {path}: {error}\n")
    return CommandResult(
        stdout="".join(output), stderr="".join(errors), status=int(bool(errors))
    )


def listing(shell: "Shell", path: str, flags: set[str], header: bool) -> str:
    """Сформировать вывод одного файла или содержимого каталога."""
    canonical = shell.vfs.resolve(path, shell.cwd)
    node = shell.vfs.nodes[canonical]
    if node.kind == "file":
        return format_entry(path, node, "l" in flags)
    entries = directory_entries(shell, canonical, "a" in flags)
    body = "".join(
        format_entry(name, shell.vfs.nodes[target], "l" in flags)
        for name, target in entries
    )
    return f"{path}:\n{body}\n" if header else body


def directory_entries(
    shell: "Shell", canonical: str, include_hidden: bool,
) -> list[tuple[str, str]]:
    """Получить имена детей, добавляя специальные записи при -a."""
    children = shell.vfs.list_dir(canonical)
    entries = [
        (basename(path), path) for path in children
        if include_hidden or not basename(path).startswith(".")
    ]
    if include_hidden:
        entries.extend([
            (".", canonical), ("..", dirname(canonical) or "/"),
        ])
    return sorted(entries)


def format_entry(name: str, node: Node, long_format: bool) -> str:
    """Показать имя, а в длинном формате также тип, права и байты."""
    if not long_format:
        return f"{name}\n"
    kind = stat.S_IFDIR if node.kind == "dir" else stat.S_IFREG
    permissions = stat.filemode(kind | node.mode)
    size = len(node.data) if node.kind == "file" else 0
    return f"{permissions} {size:>8} {name}\n"


def directory_argument(shell: "Shell", arguments: list[str]) -> str:
    """Выбрать HOME, предыдущий каталог либо единственный путь."""
    paths = arguments[1:] if arguments[:1] == ["--"] else arguments
    if len(paths) > 1:
        raise ArgumentError("cd: требуется не более одного пути")
    if not paths:
        home = shell.environment.get("HOME", "")
        if not home:
            raise VfsError("cd: переменная HOME не задана")
        return home
    path = paths[0]
    if path.startswith("-") and path != "-" and paths is arguments:
        raise ArgumentError(f"cd: неизвестный параметр {path}")
    if path == "-":
        if shell.previous_cwd is None:
            raise VfsError("cd: предыдущий каталог не задан")
        return shell.previous_cwd
    return path


def change_directory(shell: "Shell", arguments: list[str]) -> CommandResult:
    """Сменить рабочий каталог только после всех проверок доступа."""
    path = directory_argument(shell, arguments)
    canonical = shell.vfs.resolve(path, shell.cwd)
    node = shell.vfs.nodes[canonical]
    if node.kind != "dir":
        raise VfsError(f"cd: не является каталогом: {path}")
    shell.vfs.require(node, SEARCH)
    shell.previous_cwd, shell.cwd = shell.cwd, canonical
    print_path = arguments in (["-"], ["--", "-"])
    return CommandResult(stdout=f"{canonical}\n" if print_path else "")
