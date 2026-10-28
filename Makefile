.PHONY: setup build run test check fixtures

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -r requirements.lock
	.venv/bin/python -m pip install --no-deps -e .
	npm ci

build:
	npm run build

run:
	./run.sh

test:
	.venv/bin/python -m pytest
	npm test -- --run

check:
	.venv/bin/ruff check src/shell_emulator tests/python tools
	.venv/bin/python tools/check_repository.py
	npm run check

fixtures:
	.venv/bin/python tools/generate_fixtures.py
