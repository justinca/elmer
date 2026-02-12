.PHONY: up down logs build test status init-db

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

test:
	@echo "Running tests across packages..."
	cd packages/core && python -m pytest tests/ -v
	@echo "All tests passed."

status:
	@bash scripts/health-check.sh

init-db:
	@bash scripts/init-db.sh
