"""Календарь с английскими заголовками независимо от локали процесса."""

from calendar import SUNDAY, TextCalendar
from datetime import date
from typing import TYPE_CHECKING

from .errors import ArgumentError
from .models import CommandResult

if TYPE_CHECKING:
    from .engine import Shell

MIN_YEAR = 1
MAX_YEAR = 9999
MIN_MONTH = 1
MAX_MONTH = 12
YEAR_ARGUMENTS = 1
MONTH_ARGUMENTS = 2
MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
)
DAY_NAMES = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    "Sunday",
)


class EnglishCalendar(TextCalendar):
    """Форматировать календарь без чтения и переключения глобальной локали."""

    def formatweekday(self, day: int, width: int) -> str:
        """Вывести название дня из постоянного английского набора."""
        return DAY_NAMES[day][:width].center(width)

    def formatmonthname(
        self, theyear: int, themonth: int, width: int, withyear: bool = True,
    ) -> str:
        """Вывести название месяца и при необходимости год."""
        name = MONTH_NAMES[themonth - MIN_MONTH]
        if withyear:
            name = f"{name} {theyear}"
        return name.center(width)


def calendar_date(args: list[str]) -> tuple[int | None, int]:
    """Выбрать текущий месяц, год либо явно заданную пару месяц/год."""
    if len(args) > MONTH_ARGUMENTS:
        raise ArgumentError("cal: ожидается [ГОД] либо МЕСЯЦ ГОД")
    if not args:
        today = date.today()
        return today.month, today.year
    try:
        values = [int(argument) for argument in args]
    except ValueError as error:
        raise ArgumentError("cal: месяц и год должны быть числами") from error
    if len(values) == YEAR_ARGUMENTS:
        month, year = None, values[0]
    else:
        month, year = values
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ArgumentError("cal: год должен быть от 1 до 9999")
    if month is not None and not MIN_MONTH <= month <= MAX_MONTH:
        raise ArgumentError("cal: месяц должен быть от 1 до 12")
    return month, year


def cal(shell: "Shell", args: list[str]) -> CommandResult:
    """Вернуть календарь с первым днём недели воскресеньем."""
    month, year = calendar_date(args)
    calendar = EnglishCalendar(firstweekday=SUNDAY)
    output = calendar.formatyear(year) if month is None else (
        calendar.formatmonth(year, month)
    )
    return CommandResult(stdout=output)
