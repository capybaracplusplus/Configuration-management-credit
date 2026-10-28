"""Права chmod, атомарная проверка режима и рекурсивный сбор операндов."""

import pytest

from shell_emulator.commands_permissions import chmod
from shell_emulator.engine import Shell
from shell_emulator.errors import ArgumentError
from shell_emulator.vfs import Node, VirtualFS


@pytest.fixture
def shell():
    """Создать несколько независимо доступных операндов в памяти."""
    filesystem = VirtualFS()
    filesystem.nodes.update({
        "/docs": Node("dir", 0o755),
        "/docs/file": Node.file(b"file contents", 0o644),
        "/docs/sub": Node("dir", 0o750),
        "/docs/sub/note": Node.file(b"nested contents", 0o600),
        "/outside": Node.file(b"outside", 0o640),
    })
    return Shell(environment={}, vfs=filesystem)


@pytest.mark.parametrize(("mode", "expected"), [
    ("000", 0o000), ("001", 0o001), ("644", 0o644),
    ("777", 0o777), ("0750", 0o750), ("0000", 0o000),
])
def test_octal_modes(shell, mode, expected):
    """Восьмеричный режим полностью заменяет девять битов доступа."""
    assert chmod(shell, [mode, "/docs/file"]).status == 0
    assert shell.vfs.nodes["/docs/file"].mode == expected


@pytest.mark.parametrize(("initial", "mode", "expected"), [
    (0o644, "u+x", 0o744),
    (0o764, "go-rwx", 0o700),
    (0o777, "u=rw,g=r,o=", 0o640),
    (0o000, "a+rw", 0o666),
    (0o640, "ug+x", 0o750),
    (0o700, "a=", 0o000),
    (0o777, "u=", 0o077),
    (0o604, "g+w", 0o624),
    (0o764, "u-rw,g+w,o+x", 0o165),
    (0o644, "u=rw,u+x,u-w", 0o544),
    (0o600, "au+r", 0o644),
    (0o640, "u+,g-", 0o640),
])
def test_symbolic_modes_apply_in_order(shell, initial, mode, expected):
    """Изменения затрагивают только выбранные классы и идут слева направо."""
    shell.vfs.nodes["/docs/file"].mode = initial
    assert chmod(shell, [mode, "/docs/file"]).status == 0
    assert shell.vfs.nodes["/docs/file"].mode == expected


@pytest.mark.parametrize("mode", [
    "", "0", "77", "888", "1755", "7555", "rwx", "+x",
    "u+s", "u+X", "u+t", "u=g", "u", "u+x,", "u+x,,g-w", "u+x,g+q",
])
def test_invalid_modes_never_change_any_target(shell, mode):
    """Даже поздняя ошибка символической цепочки не оставляет изменений."""
    before = {path: node.mode for path, node in shell.vfs.nodes.items()}
    with pytest.raises(ArgumentError) as caught:
        chmod(shell, [mode, "/docs/file", "/outside"])
    assert caught.value.status == 2
    assert before == {path: node.mode for path, node in shell.vfs.nodes.items()}


@pytest.mark.parametrize("args", [
    [], ["644"], ["-R"], ["-r", "644", "/docs"],
    ["-x", "644", "/docs"], ["--", "644"],
])
def test_invalid_flags_and_missing_operands(shell, args):
    """Проверка вызова выполняется до любых обращений к операндам."""
    with pytest.raises(ArgumentError) as caught:
        chmod(shell, args)
    assert caught.value.status == 2


def test_recursive_zero_mode_does_not_block_its_own_traversal(shell):
    """Дерево предварительно собирается, поэтому каждый потомок получает 000."""
    result = chmod(shell, ["-R", "000", "/docs"])
    assert result.status == 0
    assert all(
        node.mode == 0 for path, node in shell.vfs.nodes.items()
        if path == "/docs" or path.startswith("/docs/")
    )
    assert shell.vfs.nodes["/outside"].mode == 0o640


def test_recursive_symbolic_modes_use_each_nodes_original_bits(shell):
    """Символическая маска применяется к индивидуальным исходным правам."""
    assert chmod(shell, ["-R", "go-rwx", "/docs"]).status == 0
    assert shell.vfs.nodes["/docs"].mode == 0o700
    assert shell.vfs.nodes["/docs/file"].mode == 0o600
    assert shell.vfs.nodes["/docs/sub"].mode == 0o700
    assert shell.vfs.nodes["/docs/sub/note"].mode == 0o600


def test_failed_recursive_preflight_preserves_whole_operand(shell):
    """Недоступный потомок запрещает частичное изменение данного операнда."""
    shell.vfs.nodes["/docs/sub"].mode = 0o000
    before = {path: node.mode for path, node in shell.vfs.nodes.items()}
    result = chmod(shell, ["-R", "777", "/docs"])
    assert result.status == 1
    assert "Доступ запрещён" in result.stderr
    assert before == {path: node.mode for path, node in shell.vfs.nodes.items()}


def test_multiple_paths_continue_after_a_failed_operand(shell):
    """Ошибка одного пути не отменяет успешные изменения остальных путей."""
    result = chmod(shell, ["600", "/missing", "/docs/file", "/outside"])
    assert result.status == 1
    assert "/missing" in result.stderr
    assert shell.vfs.nodes["/docs/file"].mode == 0o600
    assert shell.vfs.nodes["/outside"].mode == 0o600


def test_recursive_failure_does_not_prevent_next_operand(shell):
    """Следующий операнд меняется после отказа предварительного обхода."""
    shell.vfs.nodes["/docs/sub"].mode = 0o000
    result = chmod(shell, ["-R", "777", "/docs", "/outside"])
    assert result.status == 1
    assert shell.vfs.nodes["/docs"].mode == 0o755
    assert shell.vfs.nodes["/outside"].mode == 0o777


def test_owner_can_restore_zero_modes_without_target_write_permission(shell):
    """Владелец восстанавливает файл и каталог даже без их исходных прав."""
    shell.vfs.nodes["/docs/file"].mode = 0o000
    shell.vfs.nodes["/docs"].mode = 0o555
    assert chmod(shell, ["600", "/docs/file"]).status == 0
    shell.vfs.nodes["/docs"].mode = 0o000
    assert chmod(shell, ["755", "/docs/"]).status == 0
    assert shell.vfs.nodes["/docs"].mode == 0o755


def test_owner_can_restore_root_zero_mode(shell):
    """Сам корень можно восстановить без прохода по родительскому пути."""
    assert chmod(shell, ["000", "/"]).status == 0
    assert shell.vfs.nodes["/"].mode == 0o000
    assert chmod(shell, ["755", "/"]).status == 0
    assert shell.vfs.nodes["/"].mode == 0o755


def test_parent_search_is_required_for_changing_a_child(shell):
    """Владение целевым файлом не разрешает обход закрытого родителя."""
    shell.vfs.nodes["/docs"].mode = 0o600
    result = chmod(shell, ["777", "/docs/file"])
    assert result.status == 1
    assert shell.vfs.nodes["/docs/file"].mode == 0o644


def test_recursive_directory_requires_existing_read_and_search(shell):
    """Без чтения нельзя собрать рекурсивный набор до изменения прав."""
    shell.vfs.nodes["/docs"].mode = 0o111
    assert chmod(shell, ["-R", "755", "/docs"]).status == 1
    assert chmod(shell, ["755", "/docs"]).status == 0


@pytest.mark.parametrize("args", [
    ["600", "--", "-R"], ["--", "600", "-R"],
])
def test_option_terminator_allows_dash_names(shell, args):
    """После -- имя -R является путём, а не рекурсивным параметром."""
    shell.vfs.nodes["/-R"] = Node.file(b"literal option name")
    assert chmod(shell, args).status == 0
    assert shell.vfs.nodes["/-R"].mode == 0o600


def test_relative_paths_preserve_content_and_require_directory_suffix(shell):
    """Меняются только права; завершающий слеш требует тип каталога."""
    shell.cwd = "/docs"
    before = shell.vfs.nodes["/docs/file"].content_b64
    assert chmod(shell, ["600", "file"]).status == 0
    assert shell.vfs.nodes["/docs/file"].content_b64 == before
    assert chmod(shell, ["777", "file/"]).status == 1
    assert shell.vfs.nodes["/docs/file"].mode == 0o600
