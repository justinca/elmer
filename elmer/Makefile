.PHONY: up down logs logs-core logs-dash logs-knowledge logs-telegram logs-transcription \
       build restart status test test-pipeline clean shell-core db-shell init-db \
       sync-notes ingest-docs search chat transcribe sync-env \
       agents agent-run agent-logs agent-reload test-agents \
       prop spots dx pota dxcc test-radio \
       dashboard dashboard-dev dashboard-build logs-dashboard-ui

CORE_URL ?= http://localhost:8100

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

logs-knowledge:
	docker compose logs -f elmer-knowledge

logs-telegram:
	docker compose logs -f elmer-telegram

logs-transcription:
	docker compose logs -f elmer-transcription

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

test-pipeline:
	@echo "Running end-to-end knowledge pipeline tests..."
	python scripts/test-knowledge-pipeline.py

# ── Knowledge & RAG ──────────────────────────────────────────

sync-notes:
	@echo "Triggering Obsidian sync..."
	@curl -s -X POST $(CORE_URL)/knowledge/ingest/directory \
		-H 'Content-Type: application/json' \
		-d '{"path":"/app/docs","source":"elmer-docs","patterns":["*.md"]}' | python -m json.tool

ingest-docs:
	@echo "Ingesting Elmer documentation..."
	@curl -s -X POST $(CORE_URL)/knowledge/ingest/directory \
		-H 'Content-Type: application/json' \
		-d '{"path":"/app/docs","source":"elmer-docs","recursive":true,"patterns":["*.md"]}' | python -m json.tool

search:
ifndef Q
	$(error Usage: make search Q="your query here")
endif
	@curl -s -X POST $(CORE_URL)/knowledge/search \
		-H 'Content-Type: application/json' \
		-d '{"query":"$(Q)","limit":5}' | python -m json.tool

chat:
ifndef M
	$(error Usage: make chat M="your message here")
endif
	@curl -s -X POST $(CORE_URL)/chat \
		-H 'Content-Type: application/json' \
		-d '{"message":"$(M)"}' | python -m json.tool

transcribe:
ifndef F
	$(error Usage: make transcribe F="path/to/file.wav")
endif
	@echo "Uploading $(F) for transcription..."
	@curl -s -X POST $(CORE_URL)/transcription/upload \
		-F "file=@$(F)" | python -m json.tool

# ── Agents ───────────────────────────────────────────────────

agents:
	@curl -s $(CORE_URL)/agents | python3 -m json.tool

agent-run:
ifndef A
	$(error Usage: make agent-run A=agent-name)
endif
	@curl -s -X POST $(CORE_URL)/agents/$(A)/run | python3 -m json.tool

agent-logs:
ifndef A
	$(error Usage: make agent-logs A=agent-name)
endif
	@curl -s "$(CORE_URL)/agents/$(A)/runs?limit=10" | python3 -m json.tool

agent-reload:
	@curl -s -X POST $(CORE_URL)/agents/orchestrator/reload | python3 -m json.tool

test-agents:
	@python3 scripts/test-agents.py

# ── Radio Intelligence ──────────────────────────────────────

prop:
	@curl -s $(CORE_URL)/propagation | python3 -m json.tool

spots:
	@curl -s "$(CORE_URL)/dx/spots?limit=20" | python3 -m json.tool

dx:
ifndef C
	$(error Usage: make dx C=JA1ABC)
endif
	@curl -s "$(CORE_URL)/dx/entities/$(C)" | python3 -m json.tool

pota:
	@curl -s $(CORE_URL)/pota/spots | python3 -m json.tool

dxcc:
	@curl -s $(CORE_URL)/log/dxcc | python3 -m json.tool

test-radio:
	@python3 scripts/test-radio.py

# ── Dashboard UI ────────────────────────────────────────

dashboard:
	docker compose up -d elmer-dashboard-ui

dashboard-dev:
	cd packages/dashboard-ui && npm run dev

dashboard-build:
	cd packages/dashboard-ui && npm run build

logs-dashboard-ui:
	docker compose logs -f elmer-dashboard-ui

# ── Database ─────────────────────────────────────────────────

init-db:
	@bash scripts/init-db.sh

db-shell:
	psql -h 127.0.0.1 -U postgres -d elmer

# ── Environment ──────────────────────────────────────────────

sync-env:
	@bash scripts/sync-env.sh

# ── Shells ───────────────────────────────────────────────────

shell-core:
	docker compose exec elmer-core bash

# ── Cleanup ──────────────────────────────────────────────────

clean:
	docker compose down --rmi all -v --remove-orphans
