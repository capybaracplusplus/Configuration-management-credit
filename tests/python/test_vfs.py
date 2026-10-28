"""Проверки путей и прав файловой системы, полностью живущей в памяти."""

import base64

import pytest

from shell_emulator.engine import Shell
from shell_emulator.vfs import READ, SEARCH, Node, VfsError, VirtualFS


@pytest.fixture
def vfs() -> VirtualFS:
    """Создать дерево с вложенностью, скрытым именем и двоичным файлом."""
    result = VirtualFS()
    result.nodes.update({
        "/one": Node("dir", 0o755),
        "/one/two": Node("dir", 0o755),
        "/one/two/three": Node("dir", 0o755),
        "/one/two/three/data": Node.file(b"\x00\xffbinary\n"),
        "/one/.hidden": Node.file(b"hidden"),
        "/one/file": Node.file(b"file"),
    })
    return result


def test_new_vfs_is_empty_root() -> None:
    """Корень существует без архива и имеет права по умолчанию."""
    vfs = VirtualFS()
    assert list(vfs.nodes) == ["/"]
    assert vfs.get("/").mode == 0o755
    assert vfs.list_dir("/") == []


@pytest.mark.parametrize(
    ("path", "cwd", "expected"),
    [
        ("/one/two/three/data", "/", "/one/two/three/data"),
        ("two/./three/../three/data", "/one", "/one/two/three/data"),
        ("../../../..", "/one/two", "/"),
        ("//one///two/", "/", "/one/two"),
        (".", "/one", "/one"),
    ],
)
def test_resolve_walks_components(vfs, path, cwd, expected) -> None:
    """Разрешение работает на VFS и ограничивается её корнем."""
    assert vfs.resolve(path, cwd) == expected


@pytest.mark.parametrize(
    "path",
    ["", "\x00", "/missing", "/missing/..", "/one/file/..", "/one/file/"],
)
def test_invalid_paths_do_not_get_lexically_normalized(vfs, path) -> None:
    """Нормализация не скрывает отсутствующие узлы и файлы-предки."""
    with pytest.raises(VfsError):
        vfs.resolve(path)


def test_binary_data_is_base64_and_roundtrips(vfs: VirtualFS) -> None:
    """Представление base64 сохраняет нулевые и не-UTF-8 байты."""
    path = "/one/two/three/data"
    expected = b"\x00\xffbinary\n"
    assert vfs.get(path).content_b64 == base64.b64encode(expected).decode()
    assert vfs.read_file(path) == expected


def test_listing_contains_only_immediate_sorted_children(vfs: VirtualFS):
    """Список детей не смешивается с рекурсивными потомками."""
    assert vfs.list_dir("/one") == ["/one/.hidden", "/one/file", "/one/two"]


def test_ancestor_search_permission_blocks_direct_access(vfs: VirtualFS):
    """Прямой путь не обходит отсутствие права прохода предка."""
    vfs.nodes["/one/two"].mode = 0o644
    with pytest.raises(VfsError, match="Доступ запрещён"):
        vfs.read_file("/one/two/three/data")


def test_file_read_and_directory_listing_permissions(vfs: VirtualFS):
    """Чтение файлов и просмотр каталога проверяются независимо."""
    vfs.nodes["/one/file"].mode = 0o200
    with pytest.raises(VfsError):
        vfs.read_file("/one/file")
    vfs.nodes["/one"].mode = 0o100
    assert vfs.resolve("/one/file") == "/one/file"
    with pytest.raises(VfsError):
        vfs.list_dir("/one")


def test_other_and_group_permissions_do_not_grant_owner_access(vfs):
    """Модель одного владельца не использует права группы и остальных."""
    vfs.nodes["/one"].mode = 0o077
    with pytest.raises(VfsError):
        vfs.require(vfs.nodes["/one"], READ | SEARCH)


def test_root_metadata_remains_accessible_without_search(vfs: VirtualFS):
    """Метаданные корня доступны для восстановления его прав."""
    vfs.nodes["/"].mode = 0o000
    assert vfs.get("/").mode == 0o000
    with pytest.raises(VfsError):
        vfs.list_dir("/")


def test_trailing_slash_checks_type_without_target_search(vfs: VirtualFS):
    """Права закрытого каталога доступны без чтения его содержимого."""
    vfs.nodes["/one"].mode = 0o000
    assert vfs.get("/one/").kind == "dir"
    with pytest.raises(VfsError):
        vfs.list_dir("/one/")


def test_type_errors_for_reading_directory_or_listing_file(vfs: VirtualFS):
    """Операции с неверным типом узла дают диагностические ошибки."""
    with pytest.raises(VfsError, match="каталог"):
        vfs.read_file("/one")
    with pytest.raises(VfsError, match="каталог"):
        vfs.list_dir("/one/file")


def test_resolve_parent_preserves_traversal_rules(vfs: VirtualFS) -> None:
    """Создание нового имени требует существующего доступного родителя."""
    assert vfs.resolve_parent("new", "/one") == ("/one", "new")
    assert vfs.resolve_parent("/one/two/new/") == ("/one/two", "new")
    with pytest.raises(VfsError):
        vfs.resolve_parent("/one/file/../new")
    with pytest.raises(VfsError):
        vfs.resolve_parent("/missing/new")


@pytest.mark.parametrize("path", ["", "/", ".", "..", "/one/."])
def test_resolve_parent_rejects_non_creatable_names(vfs, path) -> None:
    """Специальные компоненты нельзя использовать как новое имя."""
    with pytest.raises(VfsError):
        vfs.resolve_parent(path)


def test_shell_commands_use_injected_vfs(vfs: VirtualFS):
    """Оболочка использует переданное дерево без копии на диске."""
    shell = Shell({}, vfs=vfs)
    assert shell.vfs is vfs
    assert shell.execute("ls /one").stdout == "file\ntwo\n"
