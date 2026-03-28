.PHONY: test lint generate dev clean

test:
	uv run pytest tests/ -v

test-cov:
	uv run coverage run -m pytest tests/ -v
	uv run coverage report
	uv run coverage html

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

lint-fix:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

generate:
	uv run python -m generator.generate --count 10 --output generated_docs/

dev:
	docker compose up --build

dev-down:
	docker compose down -v

clean:
	rm -rf generated_docs/ htmlcov/ .coverage .pytest_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
