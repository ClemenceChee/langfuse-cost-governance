# Deployment topologies

The analytics stack is three services — `extractor`, `api`, `frontend` — plus a
warehouse, wired to a Langfuse source. Every topology is a combination of:

1. **Where Langfuse lives** — self-hosted or Cloud.
2. **How you read it** — REST API (`LANGFUSE_MODE=api`) or direct ClickHouse
   (`LANGFUSE_MODE=clickhouse`).
3. **Which warehouse** — Postgres (default), DuckDB (local), ClickHouse (scale).

## Wiring keys

| Env var | Wires |
|---|---|
| `LANGFUSE_MODE` | `api` (REST, version-safe) or `clickhouse` (direct read, self-hosted) |
| `LANGFUSE_BASE_URL` | Langfuse URL — e.g. `http://host.docker.internal:3000`, or `https://cloud.langfuse.com` |
| `LANGFUSE_PROJECTS` | JSON list of `{id, name, public_key, secret_key}` (api mode, multi-project) |
| `LANGFUSE_CLICKHOUSE_URL` | Langfuse's own ClickHouse HTTP port (clickhouse mode) |
| `DATABASE_URL` | The **analytics** warehouse — `postgresql://`, `duckdb:///`, `clickhouse://` |

> Rule of thumb: **never point `DATABASE_URL` at Langfuse's own database.**
> The analytics warehouse is always a *separate* database (even when it shares a
> ClickHouse *server* — see Topology 5).

---

## Topology 1 — All-in-one, single host (default)

```
┌──────────────────────────────  one host  ─────────────────────────────┐
│                                                                        │
│  Langfuse (self-hosted)          Analytics stack                      │
│  ├─ web        :3000             ├─ extractor                         │
│  ├─ postgres   :5432  (Langfuse) ├─ api         :8000                 │
│  └─ clickhouse :8123  (Langfuse) ├─ frontend    :8080                 │
│                                  └─ postgres (analytics, SEPARATE)    │
│                                      ▲  DATABASE_URL                  │
└──────────────────────────────────────────────────────────────────────┘
   extractor reads Langfuse via REST (LANGFUSE_BASE_URL) ──────────────►
```

**When:** the default self-hosting case — evaluating or running for one team on
one machine.

```ini
# .env
LANGFUSE_MODE=api
LANGFUSE_BASE_URL=http://host.docker.internal:3000
LANGFUSE_PROJECTS='[{"id":"app","name":"App Assistant","public_key":"pk-lf-...","secret_key":"sk-lf-..."}]'
```

```bash
docker compose up -d --build        # analytics stack (bundled Postgres on a separate volume)
make seed
```

**Notes:** the analytics Postgres is a *different* database from Langfuse's
Postgres — same engine, separate container/volume. This is the topology running
on this machine right now.

---

## Topology 2 — Zero-server local / CI (DuckDB)

```
┌──────────────────────────────  laptop / CI  ──────────────────────────┐
│  Analytics stack                    Langfuse (Cloud, or elsewhere)    │
│  ├─ extractor  ── REST ───────────────►  https://cloud.langfuse.com    │
│  ├─ api        :8000                                                 │
│  ├─ frontend   :8080                                                 │
│  └─ DuckDB file (embedded, no server)  ◄── DATABASE_URL=duckdb:///…   │
└──────────────────────────────────────────────────────────────────────┘
```

**When:** clone-and-run on a laptop, or CI (this is what GitHub Actions runs).
No database server to install.

```ini
LANGFUSE_MODE=api
LANGFUSE_BASE_URL=https://cloud.langfuse.com     # or http://host.docker.internal:3000
LANGFUSE_PROJECTS='[ … ]'
```

```bash
docker compose -f docker-compose.duckdb.yml up -d --build
docker compose -f docker-compose.duckdb.yml run --rm api python seed_demo.py
```

**Notes:** DuckDB is single-writer — fine for one user/CI, not for concurrent
multi-user. Prefer Topology 1 or 3 for shared use.

---

## Topology 3 — Scale tier (bundled ClickHouse)

```
┌──────────────────────────────  one host  ─────────────────────────────┐
│  Langfuse (self-hosted or Cloud)      Analytics stack                 │
│  ── REST (or direct ClickHouse) ──►   ├─ extractor                    │
│                                       ├─ api        :8000             │
│                                       ├─ frontend   :8080             │
│                                       └─ clickhouse :8123 (analytics) │
│                                            ▲ DATABASE_URL             │
└──────────────────────────────────────────────────────────────────────┘
```

**When:** tens of millions of rows, months of lookback, many projects — the
columnar engine makes the `GROUP BY … SUM/COUNT` marts fast.

```bash
docker compose -f docker-compose.clickhouse.yml up -d --build
docker compose -f docker-compose.clickhouse.yml run --rm api python seed_demo.py
```

`DATABASE_URL=clickhouse://default:chpass@clickhouse:8123/analytics` is set by
the compose file; Langfuse wiring in `.env` is unchanged.

---

## Topology 4 — Langfuse Cloud + managed warehouse (SaaS-friendly)

```
┌─────────────────────  your host (or serverless)  ─────────────────────┐
│  Analytics stack                         Langfuse Cloud               │
│  ├─ extractor ───────── REST ────────────►  cloud.langfuse.com        │
│  ├─ api :8000                                                         │
│  └─ frontend :8080                                                    │
│          │                                                            │
│          ▼  DATABASE_URL                                              │
│  Managed warehouse: Neon/Supabase/RDS (postgresql://)                 │
│      or ClickHouse Cloud (clickhouse://)                              │
└──────────────────────────────────────────────────────────────────────┘
```

**When:** no self-hosted database at all; Langfuse is Cloud; you want a managed,
backed-up warehouse. This is the "global / multi-team" path.

```ini
LANGFUSE_MODE=api
LANGFUSE_BASE_URL=https://cloud.langfuse.com        # or https://cloud.us.langfuse.com
LANGFUSE_PROJECTS='[ … ]'
DATABASE_URL=postgresql://user:pass@your-db.neon.tech/analytics
# or: DATABASE_URL=clickhouse://user:pass@your-clickhouse-cloud:8443/analytics
```

Run the extractor/api against the managed warehouse (any of the compose files
with `DATABASE_URL` overridden, or on a PaaS/K8s).

---

## Topology 5 — Reuse Langfuse's own ClickHouse (advanced)

```
┌──────────────────────────────  one host  ─────────────────────────────┐
│  Langfuse (self-hosted)               Analytics stack                 │
│  └─ clickhouse :8123                  ├─ extractor                    │
│        ├─ database "langfuse"  ◄──────┤  LANGFUSE_MODE=clickhouse     │
│        └─ database "analytics" ◄──────┤  DATABASE_URL                 │
│                                       ├─ api        :8000             │
│                                       └─ frontend   :8080             │
└──────────────────────────────────────────────────────────────────────┘
```

**When:** you already run Langfuse's ClickHouse and want zero extra warehouse
infra. The extractor reads Langfuse's traces *directly* and writes the marts to
a **separate database** on the same server.

```ini
LANGFUSE_MODE=clickhouse
LANGFUSE_CLICKHOUSE_URL=http://host.docker.internal:8123
DATABASE_URL=clickhouse://user:pass@host.docker.internal:8123/analytics
```

**Trade-offs:**
- ✅ No second database to run; fastest ingestion (no API pagination).
- ⚠️ Couples the analytics warehouse to Langfuse's infra (resource contention,
  upgrade coupling).
- ⚠️ `LANGFUSE_MODE=clickhouse` reads Langfuse's **column names, which vary by
  Langfuse release** — see `extractor/clickhouse_client.py`. The REST path
  (Topologies 1–4) is version-safe.

---

## How to choose

```
Langfuse self-hosted or Cloud?
├── Self-hosted, one machine, small volume …… Topology 1 (Postgres default)
│     └── large volume / long lookback ………… Topology 3 (ClickHouse)
│           └── want zero extra infra ………… Topology 5 (reuse Langfuse's CH)
├── Cloud, no self-hosted DB ………………… Topology 4 (managed warehouse)
└── Laptop / CI / eval only …………………… Topology 2 (DuckDB)
```

Every topology uses the same services and the same `DATABASE_URL` abstraction —
only the wiring differs. See [docs/warehouse.md](warehouse.md) for the warehouse
tiers themselves.
