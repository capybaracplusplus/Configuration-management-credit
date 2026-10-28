#!/bin/sh
# Запуск из любого рабочего каталога после make setup и make build.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$PROJECT_DIR/.venv/bin/python" -m shell_emulator "$@"
