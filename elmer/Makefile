.PHONY: up down logs build test status

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
