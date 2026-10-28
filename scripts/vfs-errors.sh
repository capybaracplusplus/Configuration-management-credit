#!/bin/sh
# Проверить отсутствующий и некорректный ZIP без запуска GUI.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/tools/generate_fixtures.py"
DEMO_DIR=$(mktemp -d "${TMPDIR:-/tmp}/shell vfs missing.XXXXXX")
trap 'rm -rf "$DEMO_DIR"' EXIT HUP INT TERM
ERROR_LOG="$DEMO_DIR/error.log"

expect_failure() {
    if "$PROJECT_DIR/run.sh" "$@" > "$ERROR_LOG" 2>&1; then
        cat "$ERROR_LOG"
        printf '%s\n' 'Ошибка проверки: некорректная VFS неожиданно принята.' >&2
        exit 1
    else
        actual_status=$?
    fi
    cat "$ERROR_LOG"
    if [ "$actual_status" != 1 ]; then
        printf 'Ожидался код 1, получен %s.\n' "$actual_status" >&2
        exit 1
    fi
    case "$(cat "$ERROR_LOG")" in
        *'Ошибка запуска: Не удалось загрузить VFS'*) ;;
        *)
            printf '%s\n' 'Ошибка проверки: отсутствует диагностика загрузки VFS.' >&2
            exit 1
            ;;
    esac
    printf '%s\n' 'Получен ожидаемый код 1.'
}

expect_failure --vfs "$DEMO_DIR/missing.zip"
expect_failure --vfs "$PROJECT_DIR/.generated/vfs/invalid.zip"
expect_failure --vfs "$DEMO_DIR/missing.zip" \
    --startup-script "$PROJECT_DIR/demos/stage-3.emu"
expect_failure --vfs "$PROJECT_DIR/.generated/vfs/invalid.zip" \
    --startup-script "$PROJECT_DIR/demos/stage-3.emu"
printf '%s\n' 'Ошибки загрузки VFS обработаны корректно.'
