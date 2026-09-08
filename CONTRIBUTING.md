# Contributing

Thanks for your interest! This project turns Langfuse trace telemetry into
organization-level AI cost & governance KPIs. Contributions of warehouse
backends, KPIs, or fixes are welcome.

## Quick setup

```bash
cp .env.example .env
docker compose up -d --build
make seed          # demo data
# http://localhost:8080
```

## Run the checks locally

```bash
# Python compile check
python -m py_compile extractor/*.py api/*.py warehouse/*.py

# End-to-end smoke test (Postgres via Docker, or DuckDB with no server)
DATABASE_URL=duckdb://./ci.duckdb python scripts/smoke.py
DATABASE_URL=postgresql://analytics:analytics@localhost:5433/analytics python scripts/smoke.py

# Frontend build
cd frontend && npm ci && npm run build
```

## Adding a warehouse backend

The calculation layer (`warehouse/sql.py`) is written once against a
`Dialect`. To add a backend:

1. Add a dialect to `warehouse/dialects.py` (or subclass an existing one),
   implementing the SQL fragments that differ (casts, date functions, ratios).
2. Add a `warehouse/<backend>.py` implementing the connection/execute/insert
   contract in `warehouse/base.py`.
3. Register the URL scheme in `warehouse/__init__.py:get_warehouse`.
4. Add a smoke-test line to `.github/workflows/ci.yml`.

Supported today: **Postgres**, **DuckDB** (embedded), **ClickHouse**.

## Adding a KPI

1. Add the query builder to `warehouse/sql.py` (using dialect fragments).
2. Expose it as a method on `Warehouse` in `warehouse/base.py`.
3. Add an HTTP route in `api/kpis.py`.
4. Add the metric to `frontend/src/metrics.js` (definition + formula + why) and
   render it in the dashboard.
5. Regenerate the docs: `make docs` (writes `docs/metrics.md`).

`frontend/src/metrics.js` is the single source of truth for the metric catalog;
`docs/metrics.md` is generated from it.

## Conventions

- Keep calculation logic in SQL (`warehouse/sql.py`), not in the API layer.
- Whitelist any user-supplied column names (see `DIMENSIONS` in `api/kpis.py`).
- Never commit secrets; `.env` is gitignored. Use `.env.example` for docs.
