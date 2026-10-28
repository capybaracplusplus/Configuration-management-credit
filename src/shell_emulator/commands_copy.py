"""Проверяемое заранее копирование файлов и каталогов только в памяти."""

from dataclasses import dataclass, replace
from posixpath import basename, dirname
from typing import TYPE_CHECKING

from .errors import ArgumentError
from .models import CommandResult
from .vfs import READ, SEARCH, WRITE, Node, VfsError, VirtualFS

if TYPE_CHECKING:
    from .engine import Shell

COPY_OPERANDS = 2


@dataclass(frozen=True, slots=True)
class CopyOptions:
    """Проверенные операнды и режим рекурсивного копирования."""

    source: str
    destination: str
    recursive: bool


def copy_options(arguments: list[str]) -> CopyOptions:
    """Разобрать флаги -r/-R, разделитель -- и два пути."""
    paths: list[str] = []
    recursive = False
    options = True
    for argument in arguments:
        if options and argument == "--":
            options = False
        elif options and argument.startswith("-") and argument != "-":
            if not set(argument[1:]).issubset({"r", "R"}):
                raise ArgumentError(f"cp: неизвестный параметр {argument}")
            recursive = True
        else:
            paths.append(argument)
    if len(paths) != COPY_OPERANDS:
        raise ArgumentError("cp: требуются исходный и конечный пути")
    return CopyOptions(paths[0], paths[1], recursive)


def destination_path(
    vfs: VirtualFS, path: str, cwd: str, source: Node,
) -> str:
    """Разрешить существующий путь или новое имя доступного родителя."""
    try:
        return vfs.resolve(path, cwd)
    except VfsError:
        parent, name = vfs.resolve_parent(path, cwd)
        canonical = vfs.child_path(parent, name)
        if canonical in vfs.nodes:
            raise
        if path.endswith("/") and source.kind == "file":
            raise VfsError(f"cp: конечный каталог не существует: {path}")
        return canonical


def copy_target(shell: "Shell", options: CopyOptions, source: str) -> str:
    """Выбрать итоговое имя, учитывая копирование внутрь каталога."""
    vfs = shell.vfs
    target = destination_path(
        vfs, options.destination, shell.cwd, vfs.nodes[source],
    )
    existing = vfs.nodes.get(target)
    if existing is not None and existing.kind == "dir":
        target = vfs.child_path(target, basename(source))
    if target == source or target.startswith(source.rstrip("/") + "/"):
        raise VfsError("cp: нельзя копировать узел в себя или своего потомка")
    return target


class CopyPlan:
    """Набор независимых копий узлов, применяемый после всех проверок."""

    def __init__(self, vfs: VirtualFS, source: str, target: str) -> None:
        """Сохранить дерево-источник и подготовить пустую транзакцию."""
        self.vfs = vfs
        self.source = source
        self.target = target
        self.staged: dict[str, Node] = {}

    def build(self) -> dict[str, Node]:
        """Обойти источник итеративно и проверить каждую будущую запись."""
        pending = [(self.source, self.target)]
        while pending:
            source, target = pending.pop()
            node = self.vfs.nodes[source]
            self.vfs.require(node, READ)
            self._prepare_target(node, target)
            if node.kind == "dir":
                children = self.vfs.list_dir(source)
                pending.extend(
                    (child, self.vfs.child_path(target, basename(child)))
                    for child in reversed(children)
                )
        return self.staged

    def _prepare_target(self, source: Node, target: str) -> None:
        """Проверить тип и права назначения, затем отложить изменение."""
        existing = self.vfs.nodes.get(target)
        if existing is not None and source.kind != existing.kind:
            raise VfsError(f"cp: несовместимые типы источника и цели: {target}")
        self._parent_permissions(target, existing is None)
        if existing is not None and existing.kind == "dir":
            self.vfs.require(existing, SEARCH)
            return
        if existing is not None:
            self.vfs.require(existing, WRITE)
        self._preserve_source(target)
        mode = source.mode if existing is None else existing.mode
        self.staged[target] = replace(source, mode=mode)

    def _parent_permissions(self, target: str, creating: bool) -> None:
        """Отличить создание от перезаписи и от нового дерева копии."""
        parent = dirname(target) or "/"
        if parent in self.staged and parent not in self.vfs.nodes:
            return
        node = self.vfs.nodes[parent]
        required = SEARCH | WRITE if creating else SEARCH
        self.vfs.require(node, required)

    def _preserve_source(self, target: str) -> None:
        """Не допустить изменения источника при слиянии с его предком."""
        if target == self.source or target.startswith(self.source + "/"):
            raise VfsError("cp: слияние изменило бы исходное дерево")


def copy(shell: "Shell", arguments: list[str]) -> CommandResult:
    """Скопировать узлы атомарно, не меняя исходные узлы и ZIP-архив."""
    options = copy_options(arguments)
    source = shell.vfs.resolve(options.source, shell.cwd)
    if shell.vfs.nodes[source].kind == "dir" and not options.recursive:
        raise VfsError("cp: для копирования каталога нужен -r или -R")
    target = copy_target(shell, options, source)
    changes = CopyPlan(shell.vfs, source, target).build()
    shell.vfs.nodes.update(changes)
    return CommandResult()
