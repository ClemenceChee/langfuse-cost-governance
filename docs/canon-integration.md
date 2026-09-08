# canon ↔ dashboard integration

This repo ("AI Cost & Governance") surfaces **cost governance**; the partner
repo [`ClemenceChee/canon`](https://github.com/ClemenceChee/canon) governs
**agent behaviour** from the same Langfuse traces. They are two lenses over one
source, joined at a single data seam:

> canon **exports** its governance state as versioned JSON; this repo
> **ingests** it into the warehouse and serves it as a *Behaviour governance*
> section + Grafana panel set.

The two repositories are never merged and change nothing about each other's
stack — they meet only through the JSON contract.

## The seam (one line)

```
canon export --format json --out canon-state.json
   └── (shared volume: canon writes, dashboard mounts)
canon-ingest sidecar (polls every CANON_INGEST_INTERVAL_SECONDS, default 300s)
   └── idempotent upsert → dim_policy / fact_governance / fact_governance_divergence
   └── marts → /api/kpis/behaviour → React "Behaviour governance" + Grafana panels
```

## Run commands

### 1 · canon side (in the `canon` repo)

```sh
# a project with at least one ratified policy:
canon export --format json --out /shared/canon-state.json
# (or write-through on every promote/reject — re-export the same file)
```

`--out` writes the file atomically (0600); without it the document prints to
stdout. The document is `canon/dashboard-json v1`:

```json
{
  "version": 1,
  "project": { "id": "prj-refunds", "name": null },
  "exportedAt": "2025-09-01T12:00:00.000Z",
  "metrics": {
    "ttrpMs": 7200000,
    "precision14": { "numerator": 1, "denominator": 1, "ratio": 1.0 },
    "proposals": { "total": 3, "pending": 1, "ratified": 2, "rejected": 0, "decayed": 0 }
  },
  "policies": [
    { "ruleKey": "tool-choice:refund-lookup", "kind": "tool-choice",
      "status": "ratified", "confidence": 0.8, "promotedAt": "2025-09-01T00:00:00Z",
      "operator": "reviewer@acme", "evidenceTraces": 8 }
  ],
  "divergence": [
    { "model": "gpt-4o", "taskKey": "refund-lookup", "divergentTraces": 4, "totalTraces": 12 }
  ]
}
```

Metadata/provenance only — no `input`/`output`/`metadata`.

### 2 · dashboard side (this repo)

**One-shot ingest:**

```sh
CANON_EXPORT_DIR=/shared DATABASE_URL=duckdb://./analytics.duckdb python scripts/canon_ingest.py
```

**Sidecar (polls):**

```sh
CANON_EXPORT_DIR=/shared \
DATABASE_URL=postgresql://analytics:analytics@postgres:5432/analytics \
python api/canon_ingest_loop.py
```

**Docker (Grafana stack):**

```sh
docker compose -f docker-compose.grafana.yml up -d --build
# mounts ${CANON_EXPORT_DIR:-./canon-state} into the sidecar at /app/canon-state
```

## Warehouse schema

| Table | Grain | Key (idempotent) |
|---|---|---|
| `dim_policy` | one row per ratified policy | `rule_key` |
| `fact_governance` | one row per canon export snapshot (the aggregate metrics) | `snapshot_id` = `project_id:exported_at` |
| `fact_governance_divergence` | one row per model × task-key | `project_id, model, task_key` |

Marts (SQL views in `warehouse/sql.py`):

- `mrt_governance_daily` — the latest canon snapshot per day (proposals/
  ratifications over time).
- `mrt_policy_coverage` — ratified-policy count, total evidence-trace
  references, total distinct traces, and the coverage ratio.

## API + UI

- `GET /api/kpis/behaviour` → `{ metrics, policies, divergence }`. Empty state
  returns `200` with `ttrp_ms: null` and empty lists (never `500`).
- React: a **Behaviour governance** section (ratified policies, TTRP,
  precision@14, proposal queue, policy table, divergence-by-model).
- Grafana: a governance panel set (proposals over time, ratified policies,
  model × task divergence, policy coverage) in
  `grafana/dashboards/ai-cost-governance.json`.

## Contract refinements vs the PRD (recorded, not re-litigated)

The PRD (`docs/canon-integration-prd.md`) is a draft; the implementation made
these concrete choices, documented so nothing is silently different:

1. **Endpoint path.** The PRD names `/api/kpis/governance` for the new surface,
   but that path is already the **cost**-governance endpoint (budget/burn rate).
   The behaviour surface is therefore `/api/kpis/behaviour`. Both coexist.
2. **`project.name` is `null`.** canon v0.1 persists only the project id; the
   dashboard renders the id when the name is absent.
3. **`fact_governance` holds a per-export snapshot**, not per-policy-event rows:
   the canon export carries the aggregate metrics + the ratified-policy
   registry, not a per-rejected-policy list.
4. **Divergence = canon's tool-choice divergence**, aggregated at model ×
   task-key (the settled default). A trace is "divergent" when its agent prefers
   a non-standard tool; `totalTraces` counts every model × task trace.
5. **Coverage is approximate.** `evidenceTraces` is a per-policy count (canon
   exports counts, not trace ids), so `mrt_policy_coverage.coverage_ratio` is an
   upper bound with multiplicity — exact distinct-trace coverage would need the
   evidence trace ids on the contract.

## Idempotency

Every write is an upsert on a stable key (Postgres `ON CONFLICT`, DuckDB
`INSERT OR REPLACE`, ClickHouse `ReplacingMergeTree` + `FINAL`). Re-importing
the same export (or polling it repeatedly) never duplicates rows.
