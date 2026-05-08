.PHONY: dev gunicorn test lint security

# Flask dev server — auto-reloads, loads .env automatically (needs python-dotenv in venv)
dev:
	flask --app main run --debug --port 5000

# Gunicorn locally — matches Cloud Run (use this before pushing)
gunicorn:
	gunicorn -b 0.0.0.0:8080 --timeout 120 --reload main:app

# Run tests (config in pyproject.toml)
test:
	pytest

# Lint — warning only (config in pyproject.toml)
lint:
	ruff check .

# Security scan — mirrors the PR gate (config in pyproject.toml)
security:
	bandit -r .
	pip-audit -r requirements.txt
