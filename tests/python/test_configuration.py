"""Проверки CLI и чтения стартовых сценариев без запуска браузера."""

from pathlib import Path

import pytest

from shell_emulator.configuration import (
    Configuration,
    debug_parameters,
    load_startup,
    parse_configuration,
)


def test_defaults_do_not_require_files() -> None:
    """Запуск без параметров не зависит от входных файлов."""
    config = parse_configuration([])
    assert config == Configuration()
    assert load_startup(config) == []
    assert debug_parameters(config) == (
        "VFS: не задан\nСтартовый скрипт: не задан"
    )


@pytest.mark.parametrize(
    ("flag", "field"),
    [("--vfs", "vfs"), ("--startup-script", "startup_script")],
)
def test_each_flag_resolves_relative_path(flag, field, tmp_path, monkeypatch):
    """Пути с пробелами разрешаются относительно рабочего каталога."""
    monkeypatch.chdir(tmp_path)
    config = parse_configuration([flag, "nested/a file.txt"])
    assert getattr(config, field) == tmp_path / "nested/a file.txt"


def test_both_parameters_and_debug_output(tmp_path: Path) -> None:
    """Оба параметра независимы и видимы в отладочном выводе."""
    archive = tmp_path / "archive with spaces.zip"
    startup = tmp_path / "startup with spaces.txt"
    config = parse_configuration(
        ["--vfs", str(archive), "--startup-script", str(startup)]
    )
    assert config == Configuration(archive, startup)
    assert debug_parameters(config) == (
        f"VFS: {archive}\nСтартовый скрипт: {startup}"
    )


def test_tilde_uses_real_home(tmp_path: Path, monkeypatch) -> None:
    """Путь пользователя раскрывается до загрузки сценария."""
    monkeypatch.setenv("HOME", str(tmp_path))
    config = parse_configuration(["--vfs", "~/archive.zip"])
    assert config.vfs == tmp_path / "archive.zip"


@pytest.mark.parametrize("arguments", [["--unknown"], ["--vfs"]])
def test_invalid_cli_exits_with_status_two(arguments: list[str]) -> None:
    """Неизвестные и неполные параметры являются ошибками CLI."""
    with pytest.raises(SystemExit) as error:
        parse_configuration(arguments)
    assert error.value.code == 2


def test_help_exits_successfully(capsys) -> None:
    """Справка перечисляет оба поддерживаемых параметра."""
    with pytest.raises(SystemExit) as error:
        parse_configuration(["--help"])
    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "--vfs" in output
    assert "--startup-script" in output


def test_script_preserves_source_and_line_numbers(tmp_path: Path) -> None:
    """Пропуск комментариев не меняет координаты команд и ошибок."""
    path = tmp_path / "scenario.txt"
    path.write_text(
        '# first\n\n  ls "$HOME" # inline\n  # skipped\ncd "\nexit\n',
        encoding="utf-8",
    )
    lines = load_startup(Configuration(startup_script=path))
    assert [line.number for line in lines] == [3, 5, 6]
    assert [line.text for line in lines] == [
        '  ls "$HOME" # inline', 'cd "', "exit",
    ]
    assert all(line.source == str(path) for line in lines)


def test_missing_script_has_path_diagnostic(tmp_path: Path) -> None:
    """Отсутствующий файл даёт читаемую ошибку до создания GUI."""
    path = tmp_path / "missing.txt"
    with pytest.raises(ValueError, match=str(path)):
        load_startup(Configuration(startup_script=path))


def test_non_utf8_script_has_path_diagnostic(tmp_path: Path) -> None:
    """Повреждённый UTF-8 не выполняется частично."""
    path = tmp_path / "invalid.txt"
    path.write_bytes(b"ls\n\xff\nexit")
    with pytest.raises(ValueError, match=str(path)):
        load_startup(Configuration(startup_script=path))


def test_unreadable_script_has_path_diagnostic(tmp_path, monkeypatch) -> None:
    """Отказ чтения преобразуется в диагностическую ошибку приложения."""
    path = tmp_path / "forbidden.txt"

    def reject_read(*args, **kwargs):
        """Имитировать отказ ОС независимо от пользователя тестов."""
        raise PermissionError("Доступ запрещён")

    monkeypatch.setattr(Path, "read_text", reject_read)
    with pytest.raises(ValueError, match=str(path)):
        load_startup(Configuration(startup_script=path))


def test_directory_is_not_a_script(tmp_path: Path) -> None:
    """Путь к каталогу отклоняется при предварительном чтении."""
    with pytest.raises(ValueError, match=str(tmp_path)):
        load_startup(Configuration(startup_script=tmp_path))
