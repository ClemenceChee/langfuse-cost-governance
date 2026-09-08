# Warehouse strategy

**Decision: Postgres is the default warehouse.** ClickHouse and DuckDB are
first-class, documented tiers behind the same `DATABASE_URL` abstraction — not
separate products.

## The three tiers

| Tier | Warehouse | Compose file | When to use |
|---|---|---|---|
| **Default** | Postgres | `docker-compose.yml` | Production / self-hosted. The tool stores *aggregated* analytical tables, not raw trace events — a modest, well-indexed workload Postgres handles comfortably. |
| **Local / CI** | DuckDB (embedded) | `docker-compose.duckdb.yml` | Zero-server: clone-and-run on a laptop, or CI. Single-writer, so not for concurrent multi-user. |
| **Scale** | ClickHouse | `docker-compose.clickhouse.yml` | Tens of millions of rows, months of lookback, real-time OLAP over many projects. |

## Why Postgres is the default

1. **Adoption friction is the whole game for open source.** Every self-hoster
   already runs Postgres; every PaaS offers it one-click (Neon, Supabase, RDS,
   Fly, Railway). Making ClickHouse a hard dependency asks casual users to
   operate a second database they don't know — at zero benefit to their scale.
2. **It matches the ecosystem norm.** Langfuse itself defaults to Postgres for
   small self-hosted deployments and uses ClickHouse only at large scale. A
   tool that reads *from* Langfuse should mirror that.
3. **One less moving part** in the default compose means fewer ways for a
   first-time user to fail.

## When ClickHouse becomes right

Columnar + vectorized aggregation crushes Postgres on
`GROUP BY project, SUM(tokens), COUNT(traces)` once you're into tens of
millions of rows. It's also the natural mirror of Langfuse's own backend, and
the extractor already ships a `LANGFUSE_MODE=clickhouse` read path. The flip
condition: **multi-tenant SaaS, or genuinely globally-scaled production with
hundreds of millions of rows and long lookback** → make ClickHouse the primary
path.

## Switching is a one-line change

No code change — pick the compose file, or set `DATABASE_URL`:

```bash
# Default (Postgres)
docker compose up -d --build

# Zero-server (DuckDB)
docker compose -f docker-compose.duckdb.yml up -d --build

# Scale tier (bundled ClickHouse)
docker compose -f docker-compose.clickhouse.yml up -d --build

# Or point at an existing warehouse
DATABASE_URL=clickhouse://user:pass@host:8123/db   # (or postgresql://, duckdb:///)
```

The warehouse backend is selected in `warehouse/__init__.py:get_warehouse` by
URL scheme, with per-backend SQL in `warehouse/{postgres,duckdb,clickhouse}.py`
and dialect fragments in `warehouse/dialects.py`. To add a backend, see
`CONTRIBUTING.md`.
