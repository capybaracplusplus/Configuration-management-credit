"""Проверки реальных ls и cd на виртуальном дереве."""

import pytest

from shell_emulator.commands_navigation import change_directory, list_entries
from shell_emulator.engine import Shell
from shell_emulator.errors import ArgumentError
from shell_emulator.vfs import Node, VfsError, VirtualFS


@pytest.fixture
def shell() -> Shell:
    """Создать дерево с HOME, скрытыми и двоичными файлами."""
    vfs = VirtualFS()
    vfs.nodes.update({
        "/home": Node("dir", 0o755),
        "/home/user": Node("dir", 0o750),
        "/home/user/.hidden": Node.file(b"hidden"),
        "/home/user/alpha": Node.file("яя".encode(), 0o640),
        "/home/user/bytes": Node.file(b"\x00\xff\x01", 0o400),
        "/home/user/nested": Node("dir", 0o755),
        "/-option": Node("dir", 0o755),
    })
    result = Shell({"HOME": "/home/user"}, vfs=vfs)
    result.previous_cwd = None
    return result


def test_default_listing_uses_cwd_and_hides_dotfiles(shell: Shell):
    """Обычный ls перечисляет только видимых детей текущего каталога."""
    shell.cwd = "/home/user"
    result = list_entries(shell, [])
    assert result.stdout == "alpha\nbytes\nnested\n"
    assert result.status == 0


def test_all_listing_includes_special_and_hidden_entries(shell: Shell):
    """Флаг -a показывает специальные записи и скрытые имена."""
    result = list_entries(shell, ["-a", "/home/user"])
    assert result.stdout == ".\n..\n.hidden\nalpha\nbytes\nnested\n"


def test_long_listing_reports_permissions_and_byte_sizes(shell: Shell):
    """Размер вычисляется по байтам, а не символам или base64."""
    result = list_entries(shell, ["-al", "/home/user"])
    lines = result.stdout.splitlines()
    assert "-rw-r-----        4 alpha" in lines
    assert "-r--------        3 bytes" in lines
    assert "drwxr-x---        0 ." in lines


def test_file_operand_uses_given_path_and_accepts_hidden_file(shell: Shell):
    """Операнд-файл отображается напрямую, включая скрытое имя."""
    result = list_entries(shell, ["/home/user/.hidden"])
    assert result.stdout == "/home/user/.hidden\n"


def test_multiple_operands_keep_successful_output_after_failure(shell: Shell):
    """Ошибка одного операнда не подавляет вывод остальных."""
    result = list_entries(shell, ["/missing", "/home/user", "/home"])
    assert result.status == 1
    assert "missing" in result.stderr
    assert "/home/user:\nalpha\nbytes\nnested\n" in result.stdout
    assert "/home:\nuser\n" in result.stdout


def test_listing_rejects_unreadable_directory(shell: Shell):
    """Просмотр каталога требует чтения и прохода владельца."""
    shell.vfs.nodes["/home/user"].mode = 0o100
    result = list_entries(shell, ["/home/user"])
    assert result.status == 1
    assert "Доступ запрещён" in result.stderr


def test_option_separator_and_unknown_options(shell: Shell):
    """Разделитель позволяет обращаться к именам, начинающимся с минуса."""
    assert list_entries(shell, ["--", "-option"]).status == 0
    with pytest.raises(ArgumentError):
        list_entries(shell, ["--all"])
    with pytest.raises(ArgumentError):
        list_entries(shell, ["-q"])


def test_cd_home_relative_and_previous_directory(shell: Shell):
    """HOME и относительные пути остаются внутри VFS."""
    assert change_directory(shell, []).stdout == ""
    assert shell.cwd == "/home/user"
    assert shell.previous_cwd == "/"
    change_directory(shell, ["nested/../nested"])
    assert shell.cwd == "/home/user/nested"
    assert change_directory(shell, ["-"]).stdout == "/home/user\n"
    assert shell.previous_cwd == "/home/user/nested"


def test_cd_option_separator_and_root_clamping(shell: Shell):
    """Имена с минусом разрешены после --, а .. ограничен корнем."""
    change_directory(shell, ["--", "-option"])
    assert shell.cwd == "/-option"
    change_directory(shell, ["../../../../"])
    assert shell.cwd == "/"


@pytest.mark.parametrize("path", ["/missing", "", "/home/user/alpha/"])
def test_failed_cd_preserves_current_and_previous(shell: Shell, path: str):
    """Неудачная смена каталога не меняет состояние сеанса."""
    change_directory(shell, ["/home"])
    with pytest.raises(VfsError):
        change_directory(shell, [path])
    assert (shell.cwd, shell.previous_cwd) == ("/home", "/")


def test_cd_rejects_file_or_unsearchable_directory(shell: Shell):
    """Для cd требуется каталог с правом прохода."""
    with pytest.raises(VfsError):
        change_directory(shell, ["/home/user/alpha"])
    shell.vfs.nodes["/home/user/nested"].mode = 0o400
    with pytest.raises(VfsError):
        change_directory(shell, ["/home/user/nested/"])


def test_missing_home_and_previous_are_execution_errors(shell: Shell):
    """Отсутствие HOME и истории обрабатывается без исключений ОС."""
    shell.environment.clear()
    with pytest.raises(VfsError, match="HOME"):
        change_directory(shell, [])
    with pytest.raises(VfsError, match="предыдущий"):
        change_directory(shell, ["-"])


@pytest.mark.parametrize("arguments", [["-x"], ["/", "/home"]])
def test_cd_invalid_arguments(shell: Shell, arguments: list[str]) -> None:
    """Неподдерживаемые параметры и лишние операнды отклоняются."""
    with pytest.raises(ArgumentError):
        change_directory(shell, arguments)
