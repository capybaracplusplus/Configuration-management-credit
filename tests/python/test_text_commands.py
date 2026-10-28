"""Поведение echo и uniq: аргументы, соседство, UTF-8 и доступ в VFS."""

import pytest

from shell_emulator.commands_text import echo, uniq
from shell_emulator.engine import Shell
from shell_emulator.errors import ArgumentError, ShellError
from shell_emulator.vfs import Node, VirtualFS


@pytest.fixture
def shell():
    """Создать изолированный файл с соседними и раздельными дубликатами."""
    filesystem = VirtualFS()
    filesystem.nodes["/docs"] = Node("dir", 0o755)
    filesystem.nodes["/docs/repeated.txt"] = Node.file(
        b"alpha\nalpha\nbeta\nbeta\ngamma\nalpha\n",
    )
    return Shell(environment={}, vfs=filesystem)


@pytest.mark.parametrize(("args", "expected"), [
    ([], "\n"),
    (["hello", "world"], "hello world\n"),
    (["", "a  b", ""], " a  b \n"),
    (["-n", "hello"], "hello"),
    (["-n", "-n", "hello"], "hello"),
    (["-n"], ""),
    (["--", "-n"], "-n\n"),
    (["-n", "--", "-n"], "-n"),
    (["-e", r"one\ntwo"], "-e one\\ntwo\n"),
    (["-", "--", "-n"], "- -- -n\n"),
])
def test_echo_literals_and_optional_newline(shell, args, expected):
    """Содержимое аргументов сохраняется после обработки начальных опций."""
    assert echo(shell, args).stdout == expected


@pytest.mark.parametrize(("options", "expected"), [
    ([], "alpha\nbeta\ngamma\nalpha\n"),
    (["-d"], "alpha\nbeta\n"),
    (["-u"], "gamma\nalpha\n"),
    (["-c"], "      2 alpha\n      2 beta\n      1 gamma\n      1 alpha\n"),
    (["-cd"], "      2 alpha\n      2 beta\n"),
    (["-c", "-u"], "      1 gamma\n      1 alpha\n"),
])
def test_uniq_selects_adjacent_groups(shell, options, expected):
    """Разделённые другими строками повторы не объединяются."""
    result = uniq(shell, [*options, "/docs/repeated.txt"])
    assert result.stdout == expected
    assert result.status == 0


@pytest.mark.parametrize(("content", "expected"), [
    (b"", ""),
    (b"\n\n", "\n"),
    (b"a\na", "a"),
    (b"a\na\nb", "a\nb"),
    (b"x\r\nx\r\n", "x\r\n"),
    ("а\nа\nб".encode(), "а\nб"),
    ("a\u2028b\na\u2028b\n".encode(), "a\u2028b\n"),
])
def test_uniq_empty_unicode_and_line_endings(shell, content, expected):
    """Разделителем считается LF; последний перевод строки не добавляется."""
    shell.vfs.nodes["/sample"] = Node.file(content)
    assert uniq(shell, ["/sample"]).stdout == expected


def test_uniq_relative_paths_and_option_terminator(shell):
    """Рабочий каталог и -- позволяют читать имена, похожие на параметры."""
    shell.cwd = "/docs"
    assert uniq(shell, ["repeated.txt"]).stdout.startswith("alpha\nbeta")
    shell.vfs.nodes["/docs/-d"] = Node.file(b"a\na\n")
    assert uniq(shell, ["--", "-d"]).stdout == "a\n"
    shell.vfs.nodes["/docs/-"] = Node.file(b"file, not stdin\n")
    assert uniq(shell, ["-"]).stdout == "file, not stdin\n"


@pytest.mark.parametrize("args", [
    [], ["--"], ["one", "two"], ["-x", "/docs/repeated.txt"],
    ["-du", "/docs/repeated.txt"], ["/docs/repeated.txt", "-c"],
])
def test_uniq_invalid_arguments_have_usage_status(shell, args):
    """Плохие параметры приводят к стандартному коду ошибки аргументов."""
    with pytest.raises(ArgumentError) as caught:
        uniq(shell, args)
    assert caught.value.status == 2


@pytest.mark.parametrize("path", ["/missing", "/docs", "/unreadable"])
def test_uniq_rejects_missing_directories_and_permission_denial(shell, path):
    """Ошибки VFS передаются без попыток чтения файлов реальной ОС."""
    shell.vfs.nodes["/unreadable"] = Node.file(b"secret", 0o000)
    with pytest.raises(ShellError) as caught:
        uniq(shell, [path])
    assert caught.value.status == 1


def test_uniq_requires_search_permission_and_valid_utf8(shell):
    """Проверяются права прохода по каталогу и кодировка содержимого."""
    shell.vfs.nodes["/docs"].mode = 0o600
    with pytest.raises(ShellError, match="Доступ запрещён"):
        uniq(shell, ["/docs/repeated.txt"])
    shell.vfs.nodes["/bad"] = Node.file(b"\xff\x80")
    with pytest.raises(ShellError, match="UTF-8") as caught:
        uniq(shell, ["/bad"])
    assert caught.value.status == 1


def test_uniq_does_not_modify_original_data(shell):
    """Фильтрация является чтением и сохраняет исходное содержимое VFS."""
    before = shell.vfs.read_file("/docs/repeated.txt")
    uniq(shell, ["-c", "/docs/repeated.txt"])
    assert shell.vfs.read_file("/docs/repeated.txt") == before
