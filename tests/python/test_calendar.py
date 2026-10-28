"""Режимы календаря, високосные годы и независимость от локали."""

import calendar
from datetime import date

import pytest

from shell_emulator import commands_calendar
from shell_emulator.commands_calendar import cal
from shell_emulator.engine import Shell
from shell_emulator.errors import ArgumentError


def test_month_calendar_has_sunday_first_and_expected_leap_layout():
    """Февраль 2024 начинается в четверг и содержит 29 дней."""
    output = cal(Shell(), ["2", "2024"]).stdout
    assert output == (
        "   February 2024\n"
        "Su Mo Tu We Th Fr Sa\n"
        "             1  2  3\n"
        " 4  5  6  7  8  9 10\n"
        "11 12 13 14 15 16 17\n"
        "18 19 20 21 22 23 24\n"
        "25 26 27 28 29\n"
    )


@pytest.mark.parametrize(("year", "last_day"), [
    (1900, 28), (2000, 29), (2023, 28), (2024, 29),
])
def test_gregorian_leap_year_rules(year, last_day):
    """Вековые годы делятся на 400 для появления 29 февраля."""
    lines = cal(Shell(), ["2", str(year)]).stdout.splitlines()[2:]
    days = [int(day) for line in lines for day in line.split()]
    assert days == list(range(1, last_day + 1))


def test_whole_year_contains_every_month():
    """Один аргумент выбирает календарь всего года в трёх колонках."""
    output = cal(Shell(), ["2026"]).stdout
    for month in (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ):
        assert output.count(month) == 1
    assert "2026" in output.splitlines()[0]


def test_default_calendar_uses_current_local_month(monkeypatch):
    """Без аргументов дата берётся у внедрённого календарного источника."""
    class FixedDate(date):
        """Фиксированная текущая дата для проверки режима без аргументов."""

        @classmethod
        def today(cls):
            """Вернуть дату с однозначным месяцем и годом."""
            return cls(2024, 2, 10)

    monkeypatch.setattr(commands_calendar, "date", FixedDate)
    assert cal(Shell(), []).stdout == cal(Shell(), ["2", "2024"]).stdout


def test_month_and_weekday_names_do_not_depend_on_locale(monkeypatch):
    """Даже локализованные системные имена не меняют английский вывод."""
    monkeypatch.setattr(calendar, "month_name", ["NON_ENGLISH"] * 13)
    monkeypatch.setattr(calendar, "day_name", ["NON_ENGLISH"] * 7)
    monkeypatch.setattr(calendar, "day_abbr", ["NON_ENGLISH"] * 7)
    output = cal(Shell(), ["1", "2026"]).stdout
    assert "January 2026" in output
    assert "Su Mo Tu We Th Fr Sa" in output
    assert "NON_ENGLISH" not in output


@pytest.mark.parametrize("year", ["1", "9999"])
def test_minimum_and_maximum_years(year):
    """Объявленные граничные годы доступны во всех календарных режимах."""
    assert "December" in cal(Shell(), ["12", year]).stdout
    assert "January" in cal(Shell(), [year]).stdout


@pytest.mark.parametrize("args", [
    ["0"], ["10000"], ["-1"], ["0", "2024"], ["13", "2024"],
    ["February", "2024"], ["2.5", "2024"], ["1", "2", "3"],
    ["--help"], [""], ["2", "0"],
])
def test_invalid_dates_and_arguments_have_usage_status(args):
    """Неверные даты и число аргументов дают код ошибки использования."""
    with pytest.raises(ArgumentError) as caught:
        cal(Shell(), args)
    assert caught.value.status == 2
