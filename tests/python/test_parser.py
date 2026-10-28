"""Проверки синтаксиса оболочки и раскрытия окружения."""

import pytest

from shell_emulator.errors import ParseError
from shell_emulator.parser import parse_command

ENVIRONMENT = {"HOME": "/Users/test", "LIST": " one  two ", "EMPTY": ""}


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("", []),
        (" \t # comment", []),
        ("ls $HOME", ["ls", "/Users/test"]),
        ("ls ${HOME}/file", ["ls", "/Users/test/file"]),
        ("ls '$HOME'", ["ls", "$HOME"]),
        ('ls "$HOME"', ["ls", "/Users/test"]),
        ("ls $LIST", ["ls", "one", "two"]),
        ('ls "$LIST"', ["ls", " one  two "]),
        ("ls pre${LIST}post", ["ls", "pre", "one", "two", "post"]),
        ("ls $ABSENT $EMPTY", ["ls"]),
        ('ls "$ABSENT" \'\'', ["ls", "", ""]),
        ("ls a\"b c\"'d'", ["ls", "ab cd"]),
        (r"ls a\ b \$HOME", ["ls", "a b", "$HOME"]),
        ('ls "a#b" c#comment', ["ls", "a#b", "c"]),
        (r"ls a\#b", ["ls", "a#b"]),
        ('ls "\\q"', ["ls", "\\q"]),
        ("ls a\\\nb", ["ls", "ab"]),
        ("ls $ $1", ["ls", "$", "$1"]),
        ("ls '$(touch file)'", ["ls", "$(touch file)"]),
        ('ls "|" \'`\'', ["ls", "|", "`"]),
    ],
)
def test_parsing(line: str, expected: list[str]) -> None:
    """Сравнить аргументы с ожидаемым результатом разбора."""
    assert parse_command(line, ENVIRONMENT) == expected


@pytest.mark.parametrize(
    "line",
    [
        "ls '",
        'ls "',
        "ls \\",
        "ls ${HOME",
        "ls ${}",
        "ls ${HOME:-/}",
        "ls $(id)",
        'ls "$(id)"',
        "ls `id`",
        "ls | cd",
        "ls > file",
        "ls;cd",
        "ls && cd",
    ],
)
def test_invalid_syntax(line: str) -> None:
    """Отклонить неполный и неподдерживаемый синтаксис."""
    with pytest.raises(ParseError):
        parse_command(line, ENVIRONMENT)


def test_expansion_is_not_parsed_as_shell_code() -> None:
    """Символы из переменной не превращаются в операторы и комментарии."""
    environment = {"VALUE": "a; b#c 'd' $(id)"}
    result = parse_command("ls $VALUE", environment)
    assert result == ["ls", "a;", "b#c", "'d'", "$(id)"]


def test_expansion_attaches_prefix_and_suffix() -> None:
    """Крайние поля подстановки соединяются с соседними литералами."""
    result = parse_command("ls pre${VALUE}post", {"VALUE": "one two"})
    assert result == ["ls", "preone", "twopost"]


@pytest.mark.parametrize(
    ("line", "value", "expected"),
    [
        ('ls ""$VALUE', " a ", ["ls", "a"]),
        ('ls ""$VALUE""', " a ", ["ls", "a", ""]),
        ('ls ""$VALUE""', "\t", ["ls", ""]),
        ('ls ""$VALUE', " ", ["ls"]),
        ('ls ""$VALUE', "", ["ls", ""]),
        ('ls "" $VALUE', " a ", ["ls", "", "a"]),
        ('ls $VALUE""$VALUE', " a ", ["ls", "a", "a"]),
        ('ls ""$VALUE', "a b", ["ls", "a", "b"]),
        ('ls $VALUE""', " a", ["ls", "a"]),
    ],
)
def test_field_splitting_distinguishes_empty_quote_boundaries(
    line: str, value: str, expected: list[str],
) -> None:
    """Разделители подстановки удаляют пустое поле, но не соседний аргумент."""
    assert parse_command(line, {"VALUE": value}) == expected
