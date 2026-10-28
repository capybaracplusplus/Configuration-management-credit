"""Проверки ZIP-адаптера и неизменности физического источника."""

import hashlib
import stat
import zipfile
from pathlib import Path

import pytest

from shell_emulator.vfs import Node
from shell_emulator.vfs_zip import load_zip


def write_archive(path: Path, entries: list[tuple[str, bytes]]) -> Path:
    """Записать тестовый архив средствами стандартной библиотеки."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return path


def test_missing_and_invalid_archives_report_source(tmp_path: Path) -> None:
    """Ошибки физического ввода содержат исходный путь."""
    path = tmp_path / "missing.zip"
    with pytest.raises(ValueError, match=str(path)):
        load_zip(path)
    path.write_text("not a ZIP", encoding="utf-8")
    with pytest.raises(ValueError, match=str(path)):
        load_zip(path)


def test_none_and_minimal_archives(tmp_path: Path) -> None:
    """Пустой ZIP является допустимым минимальным деревом."""
    assert list(load_zip(None).nodes) == ["/"]
    path = write_archive(tmp_path / "minimal.zip", [])
    assert list(load_zip(path).nodes) == ["/"]


def test_implicit_directories_and_binary_files(tmp_path: Path) -> None:
    """Вложенность восстанавливается без явных записей каталогов."""
    path = write_archive(tmp_path / "deep.zip", [
        ("a/b/c/data", b"\x00\xff\xfe"), ("readme", b"hello"),
    ])
    vfs = load_zip(path)
    assert vfs.read_file("/a/b/c/data") == b"\x00\xff\xfe"
    assert vfs.nodes["/a/b"].kind == "dir"
    assert vfs.nodes["/a/b"].mode == 0o755
    assert vfs.list_dir("/") == ["/a", "/readme"]


def test_no_extraction_or_source_modification(tmp_path: Path, monkeypatch):
    """Загрузка и последующие изменения узлов не записывают архив."""
    path = write_archive(tmp_path / "source.zip", [("folder/file", b"old")])
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    def fail_extract(*args, **kwargs):
        """Прервать тест при попытке распаковки на диск."""
        raise AssertionError("ZIP extraction is forbidden")

    monkeypatch.setattr(zipfile.ZipFile, "extract", fail_extract)
    monkeypatch.setattr(zipfile.ZipFile, "extractall", fail_extract)
    vfs = load_zip(path)
    vfs.nodes["/folder/file"] = Node.file(b"changed", 0o000)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert list(tmp_path.iterdir()) == [path]
    assert load_zip(path).read_file("/folder/file") == b"old"


@pytest.mark.parametrize(
    "name",
    ["/absolute", "../escape", "a/../b", "a\\b", "C:/drive", "a//b", "./a"],
)
def test_unsafe_entry_names_are_rejected(tmp_path: Path, name: str) -> None:
    """Пути архива не могут нарушить структуру виртуального корня."""
    path = write_archive(tmp_path / "unsafe.zip", [(name, b"data")])
    with pytest.raises(ValueError, match="ZIP"):
        load_zip(path)


def test_duplicate_explicit_entries_are_rejected(tmp_path: Path) -> None:
    """Повторные записи не молча перезаписывают предыдущие данные."""
    with pytest.warns(UserWarning, match="Duplicate"):
        path = write_archive(tmp_path / "duplicate.zip", [
            ("a", b"first"), ("a", b"second"),
        ])
    with pytest.raises(ValueError, match="Дублирующая"):
        load_zip(path)


@pytest.mark.parametrize(
    "entries",
    [[("a", b"file"), ("a/b", b"child")],
     [("a/b", b"child"), ("a", b"file")]],
)
def test_file_directory_collisions_are_rejected(tmp_path, entries) -> None:
    """Порядок записей не позволяет превратить файл в каталог."""
    path = write_archive(tmp_path / "collision.zip", entries)
    with pytest.raises(ValueError):
        load_zip(path)


def unix_entry(name: str, mode: int) -> zipfile.ZipInfo:
    """Создать Unix-запись с явным типом и правами доступа."""
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = mode << 16
    return info


def test_explicit_parent_metadata_overrides_implicit_default(tmp_path):
    """Поздняя запись каталога уточняет права неявного предка."""
    path = tmp_path / "metadata.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("folder/file", b"data")
        archive.writestr(unix_entry("folder/", stat.S_IFDIR | 0o700), b"")
        archive.writestr(unix_entry("locked", stat.S_IFREG), b"secret")
    vfs = load_zip(path)
    assert vfs.nodes["/folder"].mode == 0o700
    assert vfs.nodes["/locked"].mode == 0o000


def test_missing_unix_metadata_uses_documented_defaults(tmp_path: Path):
    """Архивы не-Unix получают предсказуемые права файла и каталога."""
    path = tmp_path / "dos.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name in ["folder/", "folder/file"]:
            info = zipfile.ZipInfo(name)
            info.create_system = 0
            archive.writestr(info, b"")
    vfs = load_zip(path)
    assert vfs.nodes["/folder"].mode == 0o755
    assert vfs.nodes["/folder/file"].mode == 0o644


@pytest.mark.parametrize(
    "file_type", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR]
)
def test_special_nodes_are_rejected(tmp_path: Path, file_type: int) -> None:
    """Ссылки и устройства не могут получить доступ к реальной ОС."""
    path = tmp_path / "special.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(unix_entry("special", file_type | 0o777), b"/etc")
    with pytest.raises(ValueError, match="Специальный"):
        load_zip(path)


def test_crc_failure_is_wrapped_with_archive_path(tmp_path: Path) -> None:
    """Повреждённые данные обнаруживаются при чтении ZIP-записи."""
    path = write_archive(tmp_path / "crc.zip", [("file", b"unique payload")])
    content = path.read_bytes().replace(b"unique payload", b"broken payload")
    path.write_bytes(content)
    with pytest.raises(ValueError, match=str(path)):
        load_zip(path)
