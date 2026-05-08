.PHONY: dev gunicorn test lint security

# Flask dev server — auto-reloads on file changes, loads .env automatically
dev:
	flask --app main run --debug --port 5000

# Gunicorn locally — closest to what runs in Cloud Run (use this before pushing)
gunicorn:
	gunicorn -b 0.0.0.0:8080 --timeout 120 --reload main:app

# Run the test suite
test:
	pytest tests/ -v

# Lint (warning only — mirrors the PR check)
lint:
	ruff check .

# Security scan (mirrors the PR gate)
security:
	bandit -r . -ll --exclude .venv,tests
	pip-audit
