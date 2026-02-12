.PHONY: up down logs logs-core logs-dash build restart status test clean shell-core db-shell init-db

# ── Lifecycle ────────────────────────────────────────────────

up:
	docker compose up -d --build

down:
	docker compose down

restart:
	docker compose restart

build:
	docker compose build

# ── Logs ─────────────────────────────────────────────────────

logs:
	docker compose logs -f

logs-core:
	docker compose logs -f elmer-core

logs-dash:
	docker compose logs -f elmer-dashboard

# ── Status ───────────────────────────────────────────────────

status:
	@docker compose ps
	@echo ""
	@bash scripts/health-check.sh

# ── Testing ──────────────────────────────────────────────────

test:
	@echo "Running tests across packages..."
	cd packages/core && python -m pytest tests/ -v
	@echo ""
	@echo "All tests passed."

# ── Database ─────────────────────────────────────────────────

init-db:
	@bash scripts/init-db.sh

db-shell:
	psql -h 127.0.0.1 -U postgres -d elmer

# ── Shells ───────────────────────────────────────────────────

shell-core:
	docker compose exec elmer-core bash

# ── Cleanup ──────────────────────────────────────────────────

clean:
	docker compose down --rmi all -v --remove-orphans
