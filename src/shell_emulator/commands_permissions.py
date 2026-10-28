"""Изменение прав виртуального владельца без доступа к файлам ОС."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from .errors import ArgumentError
from .models import CommandResult
from .vfs import PERMISSION_MASK, VfsError

if TYPE_CHECKING:
    from .engine import Shell

MIN_OPERANDS = 2
CLASS_SHIFTS = {"u": 6, "g": 3, "o": 0}
ACCESS_BITS = {"r": 4, "w": 2, "x": 1}
CLASS_MASK = 0o7
OCTAL_MODE = re.compile(r"0?[0-7]{3}")
SYMBOLIC_CLAUSE = re.compile(r"([ugoa]+)([+=-])([rwx]*)")


@dataclass(frozen=True, slots=True)
class ModeClause:
    """Одна полностью проверенная символическая операция над правами."""

    mask: int
    bits: int
    operation: Literal["+", "-", "="]


type ParsedMode = int | tuple[ModeClause, ...]


def parse_clause(text: str) -> ModeClause:
    """Преобразовать явные классы и права в маски для одной операции."""
    match = SYMBOLIC_CLAUSE.fullmatch(text)
    if match is None:
        raise ArgumentError(f"chmod: неверный символический режим {text!r}")
    classes, operation, permissions = match.groups()
    shifts = {CLASS_SHIFTS[name] for name in classes.replace("a", "ugo")}
    access = sum(ACCESS_BITS[name] for name in set(permissions))
    mask = sum(CLASS_MASK << shift for shift in shifts)
    bits = sum(access << shift for shift in shifts)
    return ModeClause(mask, bits, operation)


def parse_mode(text: str) -> ParsedMode:
    """Проверить весь режим до первого изменения какого-либо узла VFS."""
    if OCTAL_MODE.fullmatch(text):
        return int(text, 8)
    return tuple(parse_clause(clause) for clause in text.split(","))


def apply_mode(current: int, mode: ParsedMode) -> int:
    """Последовательно применить операции к существующим битам доступа."""
    if isinstance(mode, int):
        return mode
    for clause in mode:
        if clause.operation == "+":
            current |= clause.bits
        elif clause.operation == "-":
            current &= ~clause.bits
        else:
            current = (current & ~clause.mask) | clause.bits
    return current & PERMISSION_MASK


def chmod_arguments(args: list[str]) -> tuple[bool, ParsedMode, list[str]]:
    """Разобрать -R, разделитель --, режим и непустой список путей."""
    recursive = False
    scanning_options = True
    operands = []
    for argument in args:
        if scanning_options and argument == "--":
            scanning_options = False
        elif scanning_options and argument == "-R":
            recursive = True
        elif scanning_options and argument.startswith("-") and argument != "-":
            raise ArgumentError(f"chmod: неизвестный параметр {argument}")
        else:
            operands.append(argument)
    if len(operands) < MIN_OPERANDS:
        raise ArgumentError("chmod: требуется режим и хотя бы один путь")
    return recursive, parse_mode(operands[0]), operands[1:]


def collect_targets(shell: "Shell", path: str, recursive: bool) -> list[str]:
    """Проверить доступ ко всему операнду до установки ограничивающих прав."""
    pending = [shell.vfs.resolve(path, shell.cwd)]
    targets = []
    while pending:
        canonical = pending.pop()
        targets.append(canonical)
        if recursive and shell.vfs.nodes[canonical].kind == "dir":
            pending.extend(reversed(shell.vfs.list_dir(canonical)))
    return targets


def chmod(shell: "Shell", args: list[str]) -> CommandResult:
    """Изменить права доступных операндов, продолжая работу после ошибок."""
    recursive, mode, paths = chmod_arguments(args)
    errors = []
    for path in paths:
        try:
            targets = collect_targets(shell, path, recursive)
            for canonical in targets:
                node = shell.vfs.nodes[canonical]
                node.mode = apply_mode(node.mode, mode)
        except VfsError as error:
            errors.append(f"chmod: {path}: {error}\n")
    return CommandResult(stderr="".join(errors), status=int(bool(errors)))
