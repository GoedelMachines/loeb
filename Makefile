.PHONY: test test-autonomous dry-run lint format install

install:
	poetry install
	poetry run playwright install chromium

test:
	poetry run pytest -q

test-autonomous:
	poetry run python -m autonomous_tester.run $(ARGS)

dry-run:
	poetry run python -m autonomous_tester.run --dry-run

lint:
	poetry run ruff check .

format:
	poetry run ruff format .

pre-commit: lint format
