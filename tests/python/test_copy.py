"""Проверки атомарного копирования и прав виртуальной файловой системы."""

from dataclasses import replace

import pytest

from shell_emulator.commands_copy import copy
from shell_emulator.engine import Shell
from shell_emulator.errors import ArgumentError
from shell_emulator.vfs import Node, VfsError, VirtualFS


@pytest.fixture
def shell() -> Shell:
    """Подготовить двоичный файл и дерево с каталогом только для чтения."""
    vfs = VirtualFS()
    vfs.nodes.update({
        "/source": Node.file(b"\x00\xffbinary\n", 0o640),
        "/destination": Node("dir", 0o755),
        "/tree": Node("dir", 0o555),
        "/tree/a": Node.file(b"first", 0o444),
        "/tree/nested": Node("dir", 0o500),
        "/tree/nested/b": Node.file(b"second", 0o600),
        "/-file": Node.file(b"option-like"),
    })
    return Shell({}, vfs=vfs)


def snapshot(vfs: VirtualFS) -> dict[str, Node]:
    """Скопировать значения узлов для сравнения состояния до ошибки."""
    return {path: replace(node) for path, node in vfs.nodes.items()}


def test_file_copy_preserves_binary_and_source(shell: Shell) -> None:
    """Копия наследует данные и права, а исходный узел не изменяется."""
    original = replace(shell.vfs.nodes["/source"])
    assert copy(shell, ["/source", "/new"]).status == 0
    assert shell.vfs.read_file("/new") == b"\x00\xffbinary\n"
    assert shell.vfs.nodes["/new"].mode == 0o640
    assert shell.vfs.nodes["/source"] == original


def test_copied_nodes_are_independent(shell: Shell) -> None:
    """Изменение прав и данных копии не меняет источник."""
    copy(shell, ["/source", "/new"])
    shell.vfs.nodes["/new"].mode = 0o000
    shell.vfs.nodes["/new"].content_b64 = ""
    assert shell.vfs.nodes["/source"].mode == 0o640
    assert shell.vfs.read_file("/source") == b"\x00\xffbinary\n"


def test_existing_directory_destination_uses_source_basename(shell: Shell):
    """Назначение-каталог получает ребёнка с именем исходного файла."""
    copy(shell, ["/source", "/destination/"])
    assert shell.vfs.read_file("/destination/source") == b"\x00\xffbinary\n"


def test_overwrite_preserves_destination_permissions(shell: Shell) -> None:
    """Перезапись меняет данные, сохраняя существующие права цели."""
    shell.vfs.nodes["/existing"] = Node.file(b"old", 0o600)
    copy(shell, ["/source", "/existing"])
    assert shell.vfs.read_file("/existing") == b"\x00\xffbinary\n"
    assert shell.vfs.nodes["/existing"].mode == 0o600


def test_overwrite_needs_file_write_but_not_parent_write(shell: Shell):
    """Доступный файл можно перезаписать в каталоге без права записи."""
    shell.vfs.nodes["/destination"].mode = 0o500
    shell.vfs.nodes["/destination/existing"] = Node.file(b"old", 0o600)
    copy(shell, ["/source", "/destination/existing"])
    assert shell.vfs.read_file("/destination/existing") == b"\x00\xffbinary\n"
    with pytest.raises(VfsError):
        copy(shell, ["/source", "/destination/new"])


@pytest.mark.parametrize("flag", ["-r", "-R", "-rR"])
def test_recursive_copy_preserves_readonly_tree(shell: Shell, flag: str):
    """Права новых каталогов не блокируют создание их собственных детей."""
    before = snapshot(shell.vfs)
    copy(shell, [flag, "/tree", "/copied/"])
    assert shell.vfs.nodes["/copied"].mode == 0o555
    assert shell.vfs.nodes["/copied/nested"].mode == 0o500
    assert shell.vfs.read_file("/copied/nested/b") == b"second"
    assert all(shell.vfs.nodes[path] == node for path, node in before.items())


def test_recursive_merge_preserves_existing_modes_and_unrelated_files(shell):
    """Слияние обновляет совпавшие файлы и сохраняет остальные узлы."""
    shell.vfs.nodes.update({
        "/destination/tree": Node("dir", 0o750),
        "/destination/tree/a": Node.file(b"old", 0o600),
        "/destination/tree/keep": Node.file(b"keep", 0o400),
    })
    copy(shell, ["-r", "/tree", "/destination"])
    assert shell.vfs.read_file("/destination/tree/a") == b"first"
    assert shell.vfs.nodes["/destination/tree/a"].mode == 0o600
    assert shell.vfs.nodes["/destination/tree"].mode == 0o750
    assert shell.vfs.read_file("/destination/tree/keep") == b"keep"


def test_relative_paths_and_option_separator(shell: Shell) -> None:
    """Пути разрешаются от cwd; -- разрешает имя с начальным минусом."""
    copy(shell, ["--", "-file", "/destination/new"])
    shell.cwd = "/destination"
    copy(shell, ["new", "../relative"])
    assert shell.vfs.read_file("/relative") == b"option-like"


@pytest.mark.parametrize(
    "arguments",
    [[], ["/source"], ["a", "b", "c"], ["-f", "/source", "/new"]],
)
def test_invalid_arguments(shell: Shell, arguments: list[str]) -> None:
    """Неверное число операндов и неизвестные флаги отклоняются."""
    with pytest.raises(ArgumentError):
        copy(shell, arguments)


@pytest.mark.parametrize(
    "arguments",
    [
        ["/source", "/source"],
        ["/source", "/./source"],
        ["-r", "/tree", "/tree/nested/copy"],
        ["-r", "/tree", "/"],
        ["-r", "/", "/destination"],
    ],
)
def test_self_and_descendant_copy_leave_vfs_unchanged(shell, arguments):
    """Канонические пути исключают самокопирование и рекурсивную ловушку."""
    before = snapshot(shell.vfs)
    with pytest.raises(VfsError):
        copy(shell, arguments)
    assert shell.vfs.nodes == before


@pytest.mark.parametrize(
    "arguments",
    [
        ["/source/", "/new"],
        ["/source", "/new/"],
        ["/source", "/source/"],
        ["/source", "/missing/../new"],
        ["/source", "/source/../new"],
        ["/missing/../source", "/new"],
        ["/source", ""],
    ],
)
def test_invalid_path_components_and_trailing_slashes(shell, arguments):
    """Лексическая нормализация не обходит ошибки реального пути VFS."""
    before = snapshot(shell.vfs)
    with pytest.raises(VfsError):
        copy(shell, arguments)
    assert shell.vfs.nodes == before


def test_directory_copy_requires_recursive_flag(shell: Shell) -> None:
    """Копирование каталога явно требует рекурсивного режима."""
    with pytest.raises(VfsError, match="-r"):
        copy(shell, ["/tree", "/new"])


def test_file_directory_type_conflicts_are_atomic(shell: Shell) -> None:
    """Файл и каталог не могут заменять друг друга при копировании."""
    shell.vfs.nodes["/destination/source"] = Node("dir", 0o755)
    before = snapshot(shell.vfs)
    with pytest.raises(VfsError):
        copy(shell, ["/source", "/destination"])
    with pytest.raises(VfsError):
        copy(shell, ["-r", "/tree", "/source"])
    assert shell.vfs.nodes == before


def test_source_and_target_file_permissions_are_enforced(shell: Shell):
    """Для файла нужны чтение источника и запись существующей цели."""
    shell.vfs.nodes["/source"].mode = 0o200
    with pytest.raises(VfsError):
        copy(shell, ["/source", "/new"])
    shell.vfs.nodes["/source"].mode = 0o400
    shell.vfs.nodes["/locked"] = Node.file(b"old", 0o400)
    with pytest.raises(VfsError):
        copy(shell, ["/source", "/locked"])
    assert shell.vfs.read_file("/locked") == b"old"


@pytest.mark.parametrize("mode", [0o400, 0o100, 0o000])
def test_recursive_source_requires_read_and_search(shell: Shell, mode: int):
    """Рекурсивное чтение требует просмотра и прохода каждого каталога."""
    shell.vfs.nodes["/tree/nested"].mode = mode
    before = snapshot(shell.vfs)
    with pytest.raises(VfsError):
        copy(shell, ["-r", "/tree", "/copied"])
    assert shell.vfs.nodes == before


def test_late_failure_rolls_back_staged_overwrite(shell: Shell) -> None:
    """Поздняя ошибка не применяет ранее проверенную перезапись файла."""
    shell.vfs.nodes.update({
        "/destination/tree": Node("dir", 0o755),
        "/destination/tree/a": Node.file(b"original", 0o600),
        "/destination/tree/nested": Node.file(b"conflict"),
    })
    before = snapshot(shell.vfs)
    with pytest.raises(VfsError):
        copy(shell, ["-r", "/tree", "/destination"])
    assert shell.vfs.nodes == before


def test_ancestor_merge_cannot_change_source_subtree(shell: Shell) -> None:
    """Слияние с предком не допускает перезаписи собственного источника."""
    shell.vfs.nodes.update({
        "/a": Node("dir", 0o755),
        "/a/a": Node("dir", 0o755),
        "/a/a/a": Node("dir", 0o755),
        "/a/a/a/file": Node.file(b"new"),
        "/a/a/file": Node.file(b"original"),
    })
    before = snapshot(shell.vfs)
    with pytest.raises(VfsError, match="исходное дерево"):
        copy(shell, ["-r", "/a/a", "/"])
    assert shell.vfs.nodes == before
