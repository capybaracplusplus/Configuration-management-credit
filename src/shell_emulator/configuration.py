"""Параметры запуска и загрузка текста командного сценария."""

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Configuration:
    """Физические пути входных файлов; отсутствие пути допустимо."""

    vfs: Path | None = None
    startup_script: Path | None = None


@dataclass(frozen=True, slots=True)
class ScriptLine:
    """Команда сценария с исходными координатами для диагностики."""

    number: int
    text: str
    source: str


def physical_path(value: str) -> Path:
    """Разрешить физический путь относительно каталога запуска."""
    try:
        return Path(value).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise argparse.ArgumentTypeError(
            f"Неверный путь {value!r}: {error}"
        ) from error


def parse_configuration(argv: list[str] | None = None) -> Configuration:
    """Прочитать параметры, сохраняя стандартные коды ошибок argparse."""
    parser = argparse.ArgumentParser(
        description="Эмулятор оболочки, вариант 12",
    )
    parser.add_argument(
        "--vfs", type=physical_path, metavar="PATH",
        help="путь к ZIP-архиву виртуальной файловой системы",
    )
    parser.add_argument(
        "--startup-script", type=physical_path, metavar="PATH",
        help="путь к стартовому сценарию UTF-8",
    )
    arguments = parser.parse_args(argv)
    return Configuration(arguments.vfs, arguments.startup_script)


def load_startup(config: Configuration) -> list[ScriptLine]:
    """Загрузить сценарий и сохранить номера исполняемых строк."""
    if config.startup_script is None:
        return []
    path = config.startup_script
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as error:
        raise ValueError(
            f"Не удалось прочитать стартовый скрипт {path}: {error}"
        ) from error
    return [
        ScriptLine(number, line, str(path))
        for number, line in enumerate(content.splitlines(), start=1)
        if line.strip() and not line.lstrip().startswith("#")
    ]


def debug_parameters(config: Configuration) -> str:
    """Сформировать одинаковый отладочный вывод для терминала и GUI."""
    vfs = str(config.vfs) if config.vfs is not None else "не задан"
    startup = (
        str(config.startup_script)
        if config.startup_script is not None else "не задан"
    )
    return f"VFS: {vfs}\nСтартовый скрипт: {startup}"
