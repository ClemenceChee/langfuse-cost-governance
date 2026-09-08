// Generates docs/metrics.md from frontend/src/metrics.js (single source of
// truth for the metric catalog). Run:  node scripts/generate-docs.mjs
import { writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  MARTS,
  METRIC_CATEGORIES,
  RAW_OBSERVATION_COLUMNS,
  RAW_SCORE_COLUMNS,
} from '../frontend/src/metrics.js'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const out = join(root, 'docs', 'metrics.md')

const L = []
const push = (...a) => L.push(...a)

push('# KPIs & Metrics Reference')
push('')
push('> Auto-generated from `frontend/src/metrics.js` — do not edit directly.')
push('> Regenerate with `node scripts/generate-docs.mjs` (or `make docs`).')
push('')
push(
  'This document defines every metric the system computes, its exact formula, and',
  'why it matters for AI cost governance. It mirrors the code: raw telemetry lands',
  'in `fact_observation` / `fact_score`, the calculation layer aggregates it into',
  '**marts** (views in `warehouse/sql.py`), and the FastAPI layer exposes them as',
  '**KPIs** (`api/kpis.py`).'
)
push('')
push('| Layer | Where | What |')
push('|---|---|---|')
push('| Raw telemetry | `fact_observation` · `fact_score` | one row per observation / score |')
push('| Marts (calculation) | `mrt_*` views in `warehouse/sql.py` | the derived grains |')
push('| KPIs (serving) | `warehouse/base.py` + `api/kpis.py` | the JSON endpoints |')
push('')
push('---')
push('')
push('## 1. Raw telemetry')
push('')
push('### `fact_observation` — one row per observation')
push('')
push('| Column | Meaning |')
push('|---|---|')
for (const [k, v] of RAW_OBSERVATION_COLUMNS) push(`| \`${k}\` | ${v} |`)
push('')
push('### `fact_score` — one row per eval result')
push('')
push('| Column | Meaning |')
push('|---|---|')
for (const [k, v] of RAW_SCORE_COLUMNS) push(`| \`${k}\` | ${v} |`)
push('')
push('---')
push('')
push('## 2. Marts — the calculation layer')
push('')
for (const m of MARTS) {
  push(`### \`${m.name}\` — ${m.grain}`)
  push('')
  if (m.note) push(m.note, '')
  push('| Field | Formula |')
  push('|---|---|')
  for (const [k, v] of m.fields) push(`| \`${k}\` | ${v} |`)
  push('')
}
push('---')
push('')
push('## 3. KPI catalog')
push('')
for (const cat of METRIC_CATEGORIES) {
  push(`### ${cat.title}`)
  push('')
  push('| KPI | Endpoint | Formula | Why it matters |')
  push('|---|---|---|---|')
  for (const m of cat.metrics) {
    push(`| **${m.name}** | \`${m.endpoint}\` | ${m.formula} | ${m.why} |`)
  }
  push('')
}
push('---')
push('')
push('## 4. Windows & conventions')
push('')
push(
  '- **MTD** (`/overview`, `/governance`): `start_time >= date_trunc(\'month\', now())`.',
  '- **Rolling window** (`/daily`, `/top`, `/sessions`, `/anomalies`): `day >= CURRENT_DATE − N days`',
  '  (or `last_seen >= now() − N days` for sessions). Default `days=30`.',
  '- **`team`** is `Unassigned` when `user_id` has no `dim_user` row or the team is empty —',
  '  this is what feeds "unattributed spend".',
  '- **Ratios are null-safe**: division by zero yields `null` (rendered as "—"), never an error.',
  '- **Costs are USD** as computed by Langfuse\'s model pricing table.'
)
push('')
push('## 5. Where each metric is computed')
push('')
push('| Metric | Mart | SQL builder |')
push('|---|---|---|')
push('| overview | `fact_observation` | `kpi_overview_mtd` + Python in `base.overview()` |')
push('| daily / top | `mrt_daily_usage` | `kpi_daily` / `kpi_top` |')
push('| efficiency | `mrt_model_efficiency` | `kpi_efficiency` |')
push('| governance | `mrt_daily_usage` + `budget` | `kpi_governance_*`, `kpi_concentration` |')
push('| sessions | `mrt_session` | `kpi_session_stats` / `kpi_sessions_top` |')
push('| anomalies | `mrt_org_daily` | `kpi_org_daily` + Python rolling baseline in `base.anomalies()` |')
push('| quality | `fact_observation` ⋈ `fact_score` | `kpi_trace_outcomes` + Python in `base.quality()` |')
push('')

writeFileSync(out, L.join('\n'))
console.log(`Wrote ${out}`)
