"""Виртуальные узлы, пути и права без обращения к файловой системе ОС."""

import base64
from dataclasses import dataclass
from posixpath import dirname
from typing import Literal

from .errors import ShellError

READ = 0o400
WRITE = 0o200
SEARCH = 0o100
DIRECTORY_MODE = 0o755
FILE_MODE = 0o644
PERMISSION_MASK = 0o777


class VfsError(ShellError):
    """Ошибка пути, типа узла или прав виртуального владельца."""


@dataclass(slots=True)
class Node:
    """Файл либо каталог с правами и сериализуемым содержимым."""

    kind: Literal["file", "dir"]
    mode: int
    content_b64: str = ""

    @classmethod
    def file(cls, content: bytes, mode: int = FILE_MODE) -> "Node":
        """Создать файл с двоичными данными в кодировке base64."""
        return cls("file", mode, base64.b64encode(content).decode("ascii"))

    @property
    def data(self) -> bytes:
        """Вернуть двоичное содержимое узла."""
        return base64.b64decode(self.content_b64, validate=True)


class VirtualFS:
    """Дерево узлов в памяти с разрешением каждого компонента пути."""

    def __init__(self) -> None:
        """Создать пустой корневой каталог."""
        self.nodes: dict[str, Node] = {"/": Node("dir", DIRECTORY_MODE)}

    @staticmethod
    def require(node: Node, permissions: int) -> None:
        """Проверить права единственного виртуального владельца."""
        if node.mode & permissions != permissions:
            raise VfsError("Доступ запрещён: недостаточно прав владельца")

    def resolve(self, path: str, cwd: str = "/") -> str:
        """Разрешить путь, проверяя существование и проход по каталогам."""
        if not path or "\x00" in path:
            raise VfsError("Пустой или недопустимый путь")
        current = "/" if path.startswith("/") else cwd
        if current not in self.nodes:
            raise VfsError(f"Рабочий каталог не существует: {current}")
        for component in path.split("/"):
            if not component:
                continue
            self._search_directory(current)
            if component == ".":
                continue
            if component == "..":
                current = dirname(current) or "/"
            else:
                current = self.child_path(current, component)
                if current not in self.nodes:
                    raise VfsError(f"Путь не существует: {path}")
        if path.endswith("/"):
            self._require_directory(current)
        return current

    def get(self, path: str, cwd: str = "/") -> Node:
        """Получить существующий узел с проверкой прохода по пути."""
        return self.nodes[self.resolve(path, cwd)]

    def read_file(self, path: str, cwd: str = "/") -> bytes:
        """Прочитать файл при наличии права чтения владельца."""
        node = self.get(path, cwd)
        if node.kind != "file":
            raise VfsError(f"Это каталог: {path}")
        self.require(node, READ)
        return node.data

    def list_dir(self, path: str, cwd: str = "/") -> list[str]:
        """Вернуть отсортированные полные пути непосредственных детей."""
        canonical = self.resolve(path, cwd)
        self._search_directory(canonical)
        self.require(self.nodes[canonical], READ)
        return sorted(
            name for name in self.nodes
            if name != canonical and dirname(name) == canonical
        )

    def resolve_parent(self, path: str, cwd: str = "/") -> tuple[str, str]:
        """Разрешить существующий родительский каталог будущего узла."""
        if not path or "\x00" in path:
            raise VfsError("Пустой или недопустимый путь")
        trimmed = path.rstrip("/")
        parent, separator, name = trimmed.rpartition("/")
        if not name or name in {".", ".."}:
            raise VfsError(f"Нельзя создать узел по пути: {path}")
        prefix = (parent or "/") if separator else "."
        canonical = self.resolve(prefix, cwd)
        self._search_directory(canonical)
        return canonical, name

    def _search_directory(self, path: str) -> None:
        """Проверить тип каталога и право прохода."""
        self._require_directory(path)
        self.require(self.nodes[path], SEARCH)

    def _require_directory(self, path: str) -> None:
        """Проверить тип, не требуя доступа к содержимому каталога."""
        node = self.nodes[path]
        if node.kind != "dir":
            raise VfsError(f"Не является каталогом: {path}")

    @staticmethod
    def child_path(parent: str, name: str) -> str:
        """Соединить канонический путь каталога и имя ребёнка."""
        return parent.rstrip("/") + "/" + name
