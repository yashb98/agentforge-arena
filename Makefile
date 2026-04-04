# AgentForge Arena — Makefile
# Run `make help` for available commands

.PHONY: help setup dev test lint type-check format clean \
        db-up db-down db-migrate tournament-duel health-check \
        challenge-validate eval-pipeline golden-hidden-url-shortener

# ============================================================
# Help
# ============================================================

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ============================================================
# Setup
# ============================================================

setup: ## Full project setup (install deps, start services, init DB)
	@echo "📦 Installing Python dependencies..."
	pip install -e ".[dev]" --break-system-packages 2>/dev/null || pip install -e ".[dev]"
	@echo "🐳 Starting Docker services..."
	docker compose up -d
	@echo "⏳ Waiting for services to be healthy..."
	sleep 5
	@echo "🗄️  Initializing database..."
	python -c "import asyncio; from packages.shared.src.db.base import init_db; asyncio.run(init_db())"
	@echo "🪣 Creating MinIO buckets..."
	docker exec arena-minio mc alias set local http://localhost:9000 minioadmin minioadmin 2>/dev/null || true
	docker exec arena-minio mc mb local/arena-artifacts 2>/dev/null || true
	docker exec arena-minio mc mb local/arena-replays 2>/dev/null || true
	@echo "✅ Setup complete! Run 'make dev' to start the API server."

dev: ## Start the API server in development mode
	uvicorn packages.api.src.main:app --reload --host 0.0.0.0 --port 8000

# ============================================================
# Quality
# ============================================================

test: ## Run all tests with coverage
	pytest packages/ --cov --cov-branch --cov-report=term-missing -v

test-fast: ## Run tests without coverage (faster)
	pytest packages/ -x -q

lint: ## Run ruff linter
	ruff check packages/

type-check: ## Run mypy type checker
	mypy packages/ --ignore-missing-imports

format: ## Format all code with ruff
	ruff format packages/
	ruff check --fix --select=I packages/

quality: lint type-check test ## Run all quality checks

challenge-validate: ## Validate all library challenges (spec, hidden_tests, judge criteria)
	python scripts/eval/validate_challenge_library.py

eval-pipeline: challenge-validate golden-hidden-url-shortener test ## CI-style: challenges + golden hidden + unit tests

golden-hidden-url-shortener: ## Run url-shortener hidden tests against golden reference app
	python scripts/eval/run_url_shortener_golden_hidden_tests.py

# ============================================================
# Database
# ============================================================

db-up: ## Start database services
	docker compose up -d postgres redis

db-down: ## Stop database services
	docker compose down

db-migrate: ## Run database migrations (Alembic)
	alembic upgrade head

db-reset: ## Reset database (drop and recreate)
	docker compose exec postgres psql -U agentforge -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	python -c "import asyncio; from packages.shared.src.db.base import init_db; asyncio.run(init_db())"

# ============================================================
# Tournament Operations
# ============================================================

tournament-duel: ## Start a 2-team duel tournament
	python -m packages.core.src.tournament.cli start --format duel

health-check: ## Check all service health
	@echo "🔍 Checking services..."
	@docker compose ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null || echo "Docker Compose not running"
	@echo ""
	@curl -sf http://localhost:8000/health | python -m json.tool 2>/dev/null || echo "API: Not running"
	@redis-cli ping 2>/dev/null || echo "Redis: Not running"
	@curl -sf http://localhost:9000/minio/health/live 2>/dev/null && echo "MinIO: OK" || echo "MinIO: Not running"

# ============================================================
# Cleanup
# ============================================================

clean: ## Clean all artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/ dist/ build/ *.egg-info

clean-all: clean ## Clean everything including Docker volumes
	docker compose down -v
