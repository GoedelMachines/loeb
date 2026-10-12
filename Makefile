.PHONY: test test-e2e dry-run check lint format install generated

install:
	poetry install
	poetry run loeb install

test:
	poetry run pytest -q

test-e2e:
	poetry run loeb run $(ARGS)

dry-run:
	poetry run loeb run --dry-run

check:
	poetry run loeb check

lint:
	poetry run ruff check .

format:
	poetry run ruff format .

pre-commit: lint format

# Rewrite skills/loeb-setup/SKILL.md and schema/loeb.schema.json after editing
# loeb/guide.md or loeb/profile.py (tests/test_guide.py fails until you do).
generated:
	poetry run python -m loeb.guide
