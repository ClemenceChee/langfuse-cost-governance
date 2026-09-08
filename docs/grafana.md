# Grafana integration

Grafana is the standard choice for orgs that already run it. Because this project
computes its KPIs as **SQL marts** (views in `warehouse/sql.py`) inside the
warehouse, Grafana can query those marts directly — no FastAPI or React needed.
You keep your existing Grafana, add one data source, and build panels from the
views.

> **Verified.** The bundled `docker-compose.grafana.yml` was tested end-to-end:
> the Postgres warehouse provisions, the `warehouse` data source health check
> returns `Database Connection OK`, and the *AI Cost & Governance* dashboard
> (12 panels) is provisioned automatically at <http://localhost:3001>.
> Note: the provisioning files under `grafana/` must be world-readable
> (mode `644`) — Grafana runs as an unprivileged user inside the container.

## Two ways to wire it in

### A. Direct SQL data source (recommended)

Point Grafana at the **analytics warehouse** and query the marts with SQL:

| Warehouse | Grafana data source |
|---|---|
| Postgres | `grafana-postgresql-datasource` (Grafana 11+; legacy `postgres` alias) |
| ClickHouse | official [`clickhouse` plugin](https://grafana.com/grafana/plugins/grafana-clickhouse-datasource/) |
| DuckDB | community plugin (local/CI only — not for shared dashboards) |

This is the cleanest path: the extractor keeps populating the warehouse, and
Grafana replaces the API + React UI. Every KPI maps to a small SQL query over a
mart.

### B. JSON API (Infinity plugin)

If you want to keep the FastAPI **semantic layer** (the `/api/kpis/*` endpoints),
add Grafana's [Infinity](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/)
plugin and point it at the API. More moving parts, but it preserves the
calculation/validation logic in `warehouse/base.py`.

## SQL recipes (map KPI → panel query)

`$__timeGroup` / `$__timeFilter` are Grafana macros; `day` is the mart's Date column.

**Cost over time**
```sql
SELECT $__timeGroup(day, '1d') AS "time", SUM(total_cost) AS "cost"
FROM mrt_org_daily WHERE $__timeFilter(day) GROUP BY 1 ORDER BY 1
```

**Tokens over time**
```sql
SELECT $__timeGroup(day, '1d') AS "time",
  SUM(input_tokens) AS "in", SUM(output_tokens) AS "out", SUM(total_tokens) AS "total"
FROM mrt_org_daily WHERE $__timeFilter(day) GROUP BY 1 ORDER BY 1
```

**Cost by project (multi-series)**
```sql
SELECT $__timeGroup(day, '1d') AS "time", project_name AS metric, SUM(total_cost) AS "value"
FROM mrt_daily_usage WHERE $__timeFilter(day) GROUP BY 1, 2 ORDER BY 1
```

**Cost by model (multi-series)** — swap `project_name` for `model`.

**Cache hit rate / reasoning share / out:in ratio over time (per model)**
```sql
SELECT $__timeGroup(day, '1d') AS "time", model AS metric, AVG(cache_hit_rate) AS "value"
FROM mrt_model_daily WHERE $__timeFilter(day) GROUP BY 1, 2 ORDER BY 1
```

**Top spenders (table)**
```sql
SELECT user_id, SUM(total_cost) AS cost, SUM(total_tokens) AS tokens
FROM mrt_daily_usage WHERE $__timeFilter(day)
GROUP BY user_id ORDER BY cost DESC LIMIT 10
```

**Budget burn (stat)** — pair with the `budget` table via a constant or a joined query.

**Model efficiency (table)**
```sql
SELECT model, cache_hit_rate, reasoning_share, output_input_ratio, cost_per_1k_tokens
FROM mrt_model_efficiency ORDER BY total_cost DESC
```

### Behaviour governance (canon)

These panels query the governance tables the `canon-ingest` sidecar populates
(see [docs/canon-integration.md](canon-integration.md) for the run commands and
the JSON contract).

**Proposals / ratifications over time**
```sql
SELECT $__timeGroup(day, '1d') AS "time",
  proposals_total AS "total", proposals_ratified AS "ratified"
FROM mrt_governance_daily WHERE $__timeFilter(day) ORDER BY 1
```

**Ratified policies (table)**
```sql
SELECT rule_key, kind, confidence, operator, evidence_traces, promoted_at
FROM dim_policy ORDER BY rule_key
```

**Decision divergence by model × task (table)**
```sql
SELECT model, task_key, divergent_traces, total_traces,
  ROUND(divergent_traces::numeric / NULLIF(total_traces, 0)::numeric, 4) AS divergence_ratio
FROM fact_governance_divergence ORDER BY model, task_key
```

**Policy coverage (table)**
```sql
SELECT ratified_policies, evidence_traces, total_traces, coverage_ratio
FROM mrt_policy_coverage
```

## Batteries-included setup

`docker-compose.grafana.yml` starts Grafana alongside the Postgres warehouse and
extractor, with the data source and a sample dashboard **auto-provisioned**:

```bash
docker compose -f docker-compose.grafana.yml up -d --build
docker compose -f docker-compose.grafana.yml run --rm api python seed_demo.py
# Grafana: http://localhost:3001 (admin / admin)
```

The sample dashboard (`grafana/dashboards/ai-cost-governance.json`) is a starting
point — import, tweak, and save your own. The SQL recipes above are what you use
to build new panels.

## Pointing an *existing* Grafana at the warehouse

1. Add a data source: *Configuration → Data sources → Add* (Postgres or ClickHouse),
   pointing at the warehouse host/port/credentials from `DATABASE_URL`.
2. Import `grafana/dashboards/ai-cost-governance.json` (Dashboards → Import), or
   hand-build panels with the SQL recipes above.
3. No code changes — Grafana reads the same `mrt_*` views the React app reads.
