"""Проверки диспетчеризации и результатов исполнения команд."""

import pytest

from shell_emulator.engine import Shell
from shell_emulator.vfs import Node


@pytest.mark.parametrize("line", ["", " # comment"])
def test_empty_input(line: str) -> None:
    """Пустой ввод не создаёт вывода и ошибок."""
    result = Shell({}).execute(line)
    assert result.stdout == result.stderr == ""
    assert result.status == 0


def test_cd_receives_expanded_arguments() -> None:
    """Раскрытие переменной определяет виртуальный рабочий каталог."""
    shell = Shell({"HOME": "/home"})
    shell.vfs.nodes["/home"] = Node("dir", 0o755)
    result = shell.execute('cd "$HOME"')
    assert result.stdout == ""
    assert shell.cwd == "/home"
    assert result.status == 0


def test_ls_accepts_combined_flags_and_option_separator() -> None:
    """Поддерживаются комбинированные флаги и путь после --."""
    shell = Shell({})
    shell.vfs.nodes["/--filename"] = Node.file(b"sample")
    result = shell.execute("ls -al -- --filename")
    assert result.status == 0
    assert "--filename" in result.stdout
    assert "-rw-r--r--" in result.stdout


@pytest.mark.parametrize(
    ("line", "status"),
    [
        ("missing", 127),
        ("ls -z", 2),
        ("ls --all", 2),
        ("cd one two", 2),
        ("exit now", 2),
        ("ls '", 2),
    ],
)
def test_errors_are_structured(line: str, status: int) -> None:
    """Ошибки возвращаются отдельно от стандартного вывода."""
    result = Shell({}).execute(line)
    assert result.status == status
    assert result.stderr.endswith("\n")
    assert result.stdout == ""
    assert not result.exit_requested


def test_exit_requests_session_shutdown() -> None:
    """Только корректная команда exit запрашивает завершение."""
    result = Shell({}).execute("exit")
    assert result.status == 0
    assert result.exit_requested


def test_environment_is_captured_on_construction() -> None:
    """Поздние изменения исходного окружения не меняют сеанс."""
    environment = {"HOME": "/initial"}
    shell = Shell(environment)
    environment["HOME"] = "/changed"
    assert shell.execute("echo $HOME").stdout == "/initial\n"
