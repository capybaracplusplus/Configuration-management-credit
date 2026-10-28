#!/bin/sh
# Сравнение SHA-256 архива и состояния VFS после перезапуска.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/tools/generate_fixtures.py"
VFS_PATH="$PROJECT_DIR/.generated/vfs/deep.zip"
DEMO_DIR=$(mktemp -d "${TMPDIR:-/tmp}/shell mutation check.XXXXXX")
trap 'rm -rf "$DEMO_DIR"' EXIT HUP INT TERM
RESET_SCRIPT="$DEMO_DIR/check original.emu"
before_hash=$(shasum -a 256 "$VFS_PATH")
printf 'Исходный ZIP: %s\n' "$before_hash"
printf '%s\n' 'Сеанс 1: просмотрите изменения и ошибки; обновите страницу, затем введите exit.'
"$PROJECT_DIR/run.sh" --vfs "$VFS_PATH" --startup-script "$PROJECT_DIR/demos/stage-5.emu"
after_hash=$(shasum -a 256 "$VFS_PATH")
if [ "$before_hash" != "$after_hash" ]; then
    printf '%s\n' 'Ошибка: исходный ZIP изменился.' >&2
    exit 1
fi
printf 'SHA-256 совпадает: %s\n' "$after_hash"
printf '%s\n' \
    'echo "Новый сеанс: права unique.txt снова 0644, строки one/two/three."' \
    'ls -l /docs/unique.txt' \
    'uniq /docs/unique.txt' \
    'echo "Сделанные копии должны отсутствовать; следующие ошибки ожидаемы."' \
    'ls /copy.txt /binary-copy.bin /tree-copy /relative-copy.txt' \
    'echo "Проверьте исходное состояние и введите exit."' > "$RESET_SCRIPT"
printf '%s\n' 'Сеанс 2: тот же ZIP без перегенерации; проверьте исходные данные и введите exit.'
"$PROJECT_DIR/run.sh" --vfs "$VFS_PATH" --startup-script "$RESET_SCRIPT"
final_hash=$(shasum -a 256 "$VFS_PATH")
if [ "$before_hash" != "$final_hash" ]; then
    printf '%s\n' 'Ошибка: исходный ZIP изменился после второго сеанса.' >&2
    exit 1
fi
printf '%s\n' 'Исходный ZIP не изменён после обоих сеансов.'
