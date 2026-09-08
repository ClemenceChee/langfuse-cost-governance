.PHONY: up down build logs ps seed reset clean duckdb duckdb-seed clickhouse clickhouse-seed grafana smoke docs canon-sample canon-ingest behaviour-api behaviour-check

# --- Behaviour governance (canon) quickstart ---
# Uses the sandbox/local venv when present, else the system interpreter.
PYTHON ?= $(if $(wildcard .deps/venv/bin/python),.deps/venv/bin/python,python3)
CANON_EXPORT_DIR ?= ./canon-state
BEHAVIOUR_DB ?= duckdb://./dsh-analytics.duckdb
API_PORT ?= 8000

# --- Postgres (default) ---
up:            ## Build and start the stack (Postgres warehouse)
	docker compose up -d --build

down:          ## Stop the stack
	docker compose down

build:         ## Build images without starting
	docker compose build

logs:          ## Tail logs
	docker compose logs -f --tail=100

ps:            ## Show running services
	docker compose ps

seed:          ## Load demo data into the warehouse
	docker compose run --rm api python seed_demo.py

# --- DuckDB (zero-server) ---
duckdb:        ## Run with an embedded DuckDB warehouse (no DB server)
	docker compose -f docker-compose.duckdb.yml up -d --build

duckdb-seed:   ## Seed the DuckDB warehouse with demo data
	docker compose -f docker-compose.duckdb.yml run --rm api python seed_demo.py

# --- ClickHouse (scale tier) ---
clickhouse:    ## Run with a bundled ClickHouse warehouse
	docker compose -f docker-compose.clickhouse.yml up -d --build

clickhouse-seed: ## Seed the ClickHouse warehouse with demo data
	docker compose -f docker-compose.clickhouse.yml run --rm api python seed_demo.py

# --- Grafana (replace the React UI) ---
grafana:       ## Run with Grafana as the dashboard (http://localhost:3001)
	docker compose -f docker-compose.grafana.yml up -d --build

# --- Verification ---
smoke:         ## End-to-end smoke test (defaults to DuckDB)
	DATABASE_URL="$${DATABASE_URL:-duckdb://./ci.duckdb}" python scripts/smoke.py

docs:          ## Regenerate docs/metrics.md from frontend/src/metrics.js
	node scripts/generate-docs.mjs

# --- Behaviour governance (canon) — local DuckDB quickstart ---
canon-sample:  ## Write a sample canon export into $(CANON_EXPORT_DIR)
	$(PYTHON) scripts/sample_canon.py $(CANON_EXPORT_DIR)/canon-state.json

canon-ingest: canon-sample ## Ingest $(CANON_EXPORT_DIR) into the warehouse (one-shot)
	CANON_EXPORT_DIR=$(CANON_EXPORT_DIR) DATABASE_URL=$(BEHAVIOUR_DB) $(PYTHON) scripts/canon_ingest.py

behaviour-api: ## Run the FastAPI layer (DuckDB) on :$(API_PORT)
	PYTHONPATH=.:api DATABASE_URL=$(BEHAVIOUR_DB) $(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port $(API_PORT)

behaviour-check: ## curl the behaviour endpoint (API must be running)
	curl -s http://localhost:$(API_PORT)/api/kpis/behaviour

reset:
	docker compose down -v

clean:
	docker compose down -v --rmi local
