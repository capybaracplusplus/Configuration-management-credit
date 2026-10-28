"""Разбор кавычек и переменных без исполнения программ реальной ОС."""

import re
from collections.abc import Mapping

from .errors import ParseError

NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
FIELD_SEPARATORS = " \t\n"
OPERATORS = "|&;<>`"
DOUBLE_ESCAPES = '$`"\\\n'


class Parser:
    """Однопроходный парсер с сохранением контекста кавычек."""

    def __init__(self, line: str, environment: Mapping[str, str]):
        """Сохранить источник, окружение и состояние текущего слова."""
        self.line = line
        self.environment = environment
        self.index = 0
        self.words: list[str] = []
        self.parts: list[str] = []
        self.active = False

    def parse(self) -> list[str]:
        """Разобрать строку на аргументы, не выполняя подстановку команд."""
        while self.index < len(self.line):
            char = self.line[self.index]
            if char in "'\"":
                self._quoted(char)
            elif char == "\\":
                self._escape(quoted=False)
            elif char == "$":
                self._expand(quoted=False)
            elif char == "#":
                break
            elif char in OPERATORS:
                raise ParseError(f"Неподдерживаемый оператор: {char}")
            elif char.isspace():
                self._finish()
                self.index += 1
            else:
                self._append(char)
                self.index += 1
        self._finish()
        return self.words

    def _append(self, value: str) -> None:
        """Добавить литерал, сохраняя в том числе пустые кавычки."""
        self.parts.append(value)
        self.active = True

    def _finish(self, *, preserve_empty: bool = True) -> None:
        """Завершить поле с учётом удаления пустых полей подстановки."""
        if self.active and (preserve_empty or any(self.parts)):
            self.words.append("".join(self.parts))
        self.parts = []
        self.active = False

    def _quoted(self, quote: str) -> None:
        """Прочитать один блок одинарных или двойных кавычек."""
        self.index += 1
        self._append("")
        while self.index < len(self.line):
            char = self.line[self.index]
            if char == quote:
                self.index += 1
                return
            if quote == '"':
                self._double_character(char)
            else:
                self._append(char)
                self.index += 1
        raise ParseError(f"Незакрытая кавычка: {quote}")

    def _double_character(self, char: str) -> None:
        """Обработать символ в двойных кавычках."""
        if char == "$":
            self._expand(quoted=True)
        elif char == "\\":
            self._escape(quoted=True)
        elif char == "`":
            raise ParseError("Подстановка команд не поддерживается")
        else:
            self._append(char)
            self.index += 1

    def _escape(self, *, quoted: bool) -> None:
        """Прочитать экранирование, учитывая правила двойных кавычек."""
        self.index += 1
        if self.index == len(self.line):
            raise ParseError("Незавершённое экранирование")
        char = self.line[self.index]
        if quoted and char not in DOUBLE_ESCAPES:
            self._append("\\")
        if char != "\n":
            self._append(char)
        self.index += 1

    def _expand(self, *, quoted: bool) -> None:
        """Раскрыть переменную; только вне кавычек разделять поля."""
        value = self._variable()
        if quoted:
            self._append(value)
            return
        for char in value:
            if char in FIELD_SEPARATORS:
                self._finish(preserve_empty=False)
            else:
                self._append(char)

    def _variable(self) -> str:
        """Прочитать имя переменной или вернуть буквальный доллар."""
        self.index += 1
        if self.index == len(self.line):
            return "$"
        char = self.line[self.index]
        if char == "(":
            raise ParseError("Подстановка команд не поддерживается")
        if char == "{":
            return self._braced_variable()
        match = NAME.match(self.line, self.index)
        if match is None:
            return "$"
        self.index = match.end()
        return self.environment.get(match.group(), "")

    def _braced_variable(self) -> str:
        """Прочитать строгое имя в конструкции ${NAME}."""
        end = self.line.find("}", self.index + 1)
        if end == -1:
            raise ParseError("Незакрытая подстановка переменной")
        name = self.line[self.index + 1 : end]
        if NAME.fullmatch(name) is None:
            raise ParseError(f"Неверное имя переменной: {name!r}")
        self.index = end + 1
        return self.environment.get(name, "")


def parse_command(line: str, environment: Mapping[str, str]) -> list[str]:
    """Преобразовать строку в имя команды и её аргументы."""
    return Parser(line, environment).parse()
