"""Загрузка ZIP в память без распаковки и изменения источника."""

import re
import stat
import zipfile
import zlib
from pathlib import Path

from .vfs import DIRECTORY_MODE, FILE_MODE, PERMISSION_MASK, Node, VirtualFS

UNIX_CREATOR = 3
UNIX_MODE_SHIFT = 16
DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
ARCHIVE_ERRORS = (
    OSError, ValueError, RuntimeError, NotImplementedError, EOFError,
    zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error,
)


def entry_path(info: zipfile.ZipInfo) -> str:
    """Проверить имя ZIP до создания какого-либо виртуального узла."""
    name = info.orig_filename
    if not name or name.startswith("/") or "\\" in name or "\x00" in name:
        raise ValueError(f"Недопустимый путь ZIP: {name!r}")
    if DRIVE_PREFIX.match(name):
        raise ValueError(f"Путь ZIP содержит имя диска: {name!r}")
    normalized = name[:-1] if name.endswith("/") else name
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError(f"Недопустимый компонент пути ZIP: {name!r}")
    return "/" + normalized


def entry_node(info: zipfile.ZipInfo, content: bytes) -> Node:
    """Преобразовать Unix-метаданные; специальные узлы отклоняются."""
    unix_mode = info.external_attr >> UNIX_MODE_SHIFT
    is_unix = info.create_system == UNIX_CREATOR
    file_type = stat.S_IFMT(unix_mode) if is_unix else 0
    if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise ValueError(f"Специальный узел ZIP: {info.filename}")
    is_directory = info.is_dir() or file_type == stat.S_IFDIR
    if info.is_dir() and file_type == stat.S_IFREG:
        raise ValueError(f"Несогласованный тип узла ZIP: {info.filename}")
    default_mode = DIRECTORY_MODE if is_directory else FILE_MODE
    mode = unix_mode & PERMISSION_MASK
    if info.create_system != UNIX_CREATOR or not (file_type or mode):
        mode = default_mode
    return Node("dir", mode) if is_directory else Node.file(content, mode)


def ensure_parents(vfs: VirtualFS, path: str) -> None:
    """Создать неявные каталоги и отклонить пересечение с файлом."""
    parent = ""
    for part in path.strip("/").split("/")[:-1]:
        parent += "/" + part
        existing = vfs.nodes.get(parent)
        if existing is not None and existing.kind != "dir":
            raise ValueError(f"Файл использован как каталог: {parent}")
        if existing is None:
            vfs.nodes[parent] = Node("dir", DIRECTORY_MODE)


def add_entry(vfs: VirtualFS, path: str, node: Node) -> None:
    """Добавить запись, разрешая уточнение неявного каталога."""
    ensure_parents(vfs, path)
    existing = vfs.nodes.get(path)
    if existing is not None and (node.kind != "dir" or existing.kind != "dir"):
        raise ValueError(f"Коллизия файла и каталога: {path}")
    vfs.nodes[path] = node


def read_archive(archive: zipfile.ZipFile) -> VirtualFS:
    """Загрузить все записи, проверяя дубликаты и контрольные суммы."""
    vfs = VirtualFS()
    explicit: set[str] = set()
    for info in archive.infolist():
        path = entry_path(info)
        if path in explicit:
            raise ValueError(f"Дублирующая запись ZIP: {path}")
        explicit.add(path)
        content = archive.read(info)
        add_entry(vfs, path, entry_node(info, content))
    return vfs


def load_zip(path: Path | None) -> VirtualFS:
    """Прочитать архив целиком либо создать пустую VFS без источника."""
    if path is None:
        return VirtualFS()
    try:
        with zipfile.ZipFile(path, "r") as archive:
            return read_archive(archive)
    except ARCHIVE_ERRORS as error:
        raise ValueError(f"Не удалось загрузить VFS {path}: {error}") from error
