# PRD — canon ↔ AI Cost & Governance Dashboard integration

> Status: proposed. Hand this to a fresh agent as a self-contained brief.
> Owner repo: `ClemenceChee/langfuse-cost-governance` (this repo). Partner repo:
> `ClemenceChee/canon`.

## Objective

Surface **behaviour governance** alongside **cost governance** in one dashboard,
sharing one Langfuse source, without merging the two codebases.

Today the dashboard answers *"what is this costing, how efficient is it?"* and
canon answers *"what did the agent decide, and should that behaviour become
policy?"*. The integration makes them two lenses over the same traces: a new
**Behaviour governance** section sits next to the existing cost KPIs.

## Background

- **`langfuse-cost-governance` (this repo)** — Python. Extractor → pluggable
  warehouse (Postgres/DuckDB/ClickHouse) → SQL marts (`mrt_*`) → FastAPI
  (`/api/kpis/*`) → React dashboard (+ optional Grafana). Reads Langfuse
  Observations v2 / Scores v3. Cost/efficiency KPIs only.
- **`canon`** — TypeScript/Node CLI. Reads Langfuse, extracts **decision facts**
  from `TOOL`/`AGENT` spans, finds divergence, proposes behavioural policies
  (confidence + trace evidence), human ratifies, lands in a versioned canon,
  exports guard-rule packs. State lives in a per-project `.canon/` dir
  (`audit.jsonl`, `proposals/`, `canon/`). Its own metrics: TTRP and
  `precision14`.

Both already read the **same** Langfuse v4 surfaces (this repo's extractor was
migrated to v2 observations / v3 scores — commit `ae5a37c`).

## Integration decision (the seam)

**Don't merge repos.** canon stays the behaviour engine; the dashboard stays the
BI layer. They meet at one data seam:

> canon **exports** its governance state; the dashboard **ingests** it into the
> warehouse and serves it as a new tab.

This is deliberately the smallest decoupled join. canon gains an `export`
surface; the dashboard gains new tables + marts + endpoints + one UI tab. No
shared runtime, no code duplication beyond the contract.

## Non-goals (explicit)

- Do **not** merge the two repositories or rewrite one in the other's stack.
- Do **not** make canon a dashboard backend, or the dashboard a policy editor.
- Do **not** change canon's core (decision extraction, proposal scoring,
  ratification workflow) — only add an export.
- Do **not** route cost into canon (canon is not a cost product).
- Enforcement is out of scope (canon already exports guard-rule packs to the
  enforcement plane; the dashboard only *displays* governance state).

## Proposed slices (vertical, canon's own discipline)

### Slice 1 — canon export surface
- Add `canon export --format json --out <path>` (and/or write on every
  `governance promote`/`reject`).
- Output one self-contained document per project: project id/name, metrics
  (TTRP, precision14, proposal counts by status), ratified policies
  (ruleKey, kind, status, confidence, promotedAt, operator, evidence count),
  and decision-divergence aggregates (per model and per task-key).

### Slice 2 — warehouse ingest
- New tables in `warehouse/sql.py`: `fact_governance` (policy/proposal events,
  one row per ratified/rejected policy) and `dim_policy` (ratified policy
  registry). Idempotent upsert, mirroring the existing `fact_observation` path.
- A small `canon_ingest` step (reuse the extractor's warehouse plumbing) that
  reads the export JSON and upserts. Runs as an optional sidecar, mirroring the
  DSH `dsh-ingest` service added in this repo.

### Slice 3 — marts + API
- New marts: `mrt_governance_daily` (proposals/ratifications over time),
  `mrt_policy_coverage` (share of traces/tokens covered by ratified policies).
- New endpoints in `api/kpis.py` (e.g. `/governance`), consistent with the
  existing KPI endpoint style and sanitization rules.

### Slice 4 — UI
- React: a **Behaviour governance** section (new tab or section within the
  Dashboard tab) showing ratified policy count, TTRP, precision14, proposal
  queue, and divergence by model — alongside the existing cost sections.
- Grafana: a governance panel set in `grafana/dashboards/ai-cost-governance.json`
  (or a second dashboard) querying the new marts.

## Data contract (draft, to be finalised in Slice 1)

`canon export` emits JSON with this shape (stable, versioned):

```json
{
  "version": 1,
  "project": { "id": "prj", "name": "Refunds" },
  "exportedAt": "2026-09-08T00:00:00Z",
  "metrics": {
    "ttrpMs": 123456,
    "precision14": { "numerator": 5, "denominator": 7, "ratio": 0.7143 },
    "proposals": { "total": 10, "pending": 3, "ratified": 5, "rejected": 2, "decayed": 0 }
  },
  "policies": [
    { "ruleKey": "tool-choice:refund-lookup", "kind": "tool-choice", "status": "ratified",
      "confidence": 0.8, "promotedAt": "2026-09-01T00:00:00Z", "operator": "reviewer@acme",
      "evidenceTraces": 8 }
  ],
  "divergence": [
    { "model": "gpt-4o", "taskKey": "refund-lookup", "divergentTraces": 4, "totalTraces": 12 }
  ]
}
```

The dashboard ingests `metrics` + `policies` into `fact_governance`/`dim_policy`
and `divergence` into a model/task aggregate. Field names above are the
starting contract; Slice 1 may refine them but must keep them JSON-serialisable
and versioned.

## Acceptance criteria

1. `canon export` produces valid, versioned JSON for a project with ≥1 ratified
   policy, and for an empty project (empty arrays, `ttrpMs: null`).
2. The dashboard ingests the export idempotently (re-import does not duplicate).
3. `/api/kpis/governance` returns the metrics + policies with the same error
   handling/sanitization as existing endpoints; empty state returns 200, not 500.
4. The React dashboard shows a Behaviour governance section that renders the
   metrics, and shows a sensible empty state when no canon data exists.
5. The Grafana governance panels query the new marts and return rows.
6. `scripts/smoke.py` covers the new endpoint(s) across all three warehouse
   backends (Postgres/DuckDB/ClickHouse).
7. Docs updated: `docs/grafana.md` (new panels), README (new section + the
   export/ingest run commands), and a short `docs/canon-integration.md`.

## Decisions already made (do not re-litigate)

- Integrate, don't merge (this PRD's whole premise).
- Seam = canon export → dashboard ingest (not a shared service, not a monorepo).
- canon is a TypeScript CLI; the dashboard is Python. Neither changes stack.
- The dashboard already reads Langfuse v2/v3 (`ae5a37c`); canon reads the same
  surfaces — they are API-aligned.
- Idempotent upserts, dialect-safe SQL (one SQL written against `warehouse/
  dialects.py`), and the existing `_sanitize` allowlist are the house rules for
  any new SQL/endpoints.

## Resolved defaults (decided 2026-09-08)

These were open questions; the human approved the following defaults. Treat
them as settled — do not re-open unless implementation reveals a hard blocker.

1. **Export transport** — file on a shared volume. canon writes
   `canon-state.json` (or `<project>.json`) to a directory the dashboard mounts.
   A `canon-ingest` sidecar in the dashboard (mirroring the existing
   `dsh-ingest` service) polls the file and upserts. No HTTP endpoint in canon,
   no polling from the API — least moving parts.
2. **Freshness** — canon writes through on every `governance promote`/`reject`;
   the sidecar polls every `SYNC_INTERVAL_SECONDS` (default 300s), matching the
   extractor cadence. Governance state is thus at most one interval stale.
3. **Divergence granularity** — **model × task-key**. canon's divergence scan
   already keys on `taskKey` + model, so exporting the aggregate is cheap and
   it is the natural unit for "behaviour policy coverage".
4. **Auth/privacy** — export metadata only. No `input`/`output`/`metadata`
   (canon already redacts io; never re-introduce it). Keep `operator`
   (governance actor), `ruleKey`, `confidence`, `evidenceTraces`. Trace ids are
   trace-level identifiers already present in the warehouse's
   `fact_observation.trace_id`, so they add no new sensitive surface.
