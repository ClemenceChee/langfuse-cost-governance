// Structured copy of docs/topologies.md, rendered by the in-app Deployment tab.

export const WIRING_KEYS = [
  ['LANGFUSE_MODE', 'api (REST, version-safe) or clickhouse (direct read, self-hosted)'],
  ['LANGFUSE_BASE_URL', 'Langfuse URL — e.g. http://host.docker.internal:3000, or https://cloud.langfuse.com'],
  ['LANGFUSE_PROJECTS', 'JSON list of {id, name, public_key, secret_key} (api mode, multi-project)'],
  ['LANGFUSE_CLICKHOUSE_URL', "Langfuse's own ClickHouse HTTP port (clickhouse mode)"],
  ['DATABASE_URL', 'The analytics warehouse — postgresql://, duckdb:///, clickhouse://'],
]

export const TOPOLOGIES = [
  {
    name: 'Topology 1 — All-in-one, single host',
    tag: 'default',
    when: 'The default self-hosting case — evaluating or running for one team on one machine.',
    diagram: [
      'one host',
      '───────────────────────────────────────────────────────────',
      'Langfuse (self-hosted)            Analytics stack',
      '  web          :3000                extractor',
      '  postgres     :5432   (Langfuse)   api        :8000',
      '  clickhouse   :8123   (Langfuse)   frontend   :8080',
      '                                    postgres (analytics, SEPARATE)',
      '',
      'extractor ── REST ──► Langfuse web      (LANGFUSE_BASE_URL)',
      'warehouse ◄── DATABASE_URL ──► analytics postgres',
    ].join('\n'),
    env: [
      'LANGFUSE_MODE=api',
      'LANGFUSE_BASE_URL=http://host.docker.internal:3000',
      'LANGFUSE_PROJECTS=\'[{"id":"app","name":"App Assistant","public_key":"pk-lf-...","secret_key":"sk-lf-..."}]\'',
    ].join('\n'),
    commands: [
      'docker compose up -d --build',
      'make seed',
    ].join('\n'),
    notes: [
      'The analytics Postgres is a different database from Langfuse\u2019s Postgres — same engine, separate container/volume.',
      'This is the topology running on this machine right now.',
    ],
  },
  {
    name: 'Topology 2 — Zero-server local / CI',
    tag: 'duckdb',
    when: 'Clone-and-run on a laptop, or CI. No database server to install.',
    diagram: [
      'laptop / CI',
      '───────────────────────────────────────────────────────────',
      'Analytics stack                   Langfuse (Cloud / elsewhere)',
      '  extractor ── REST ────────────────►  cloud.langfuse.com',
      '  api          :8000',
      '  frontend     :8080',
      '  DuckDB file (embedded, no server)  ◄── DATABASE_URL=duckdb:///',
    ].join('\n'),
    env: [
      'LANGFUSE_MODE=api',
      'LANGFUSE_BASE_URL=https://cloud.langfuse.com',
      'LANGFUSE_PROJECTS=\'[ … ]\'',
    ].join('\n'),
    commands: [
      'docker compose -f docker-compose.duckdb.yml up -d --build',
      'docker compose -f docker-compose.duckdb.yml run --rm api python seed_demo.py',
    ].join('\n'),
    notes: [
      'DuckDB is single-writer — fine for one user/CI, not concurrent multi-user.',
      'This is what GitHub Actions CI runs.',
    ],
  },
  {
    name: 'Topology 3 — Scale tier (bundled ClickHouse)',
    tag: 'clickhouse',
    when: 'Tens of millions of rows, months of lookback, many projects.',
    diagram: [
      'one host',
      '───────────────────────────────────────────────────────────',
      'Langfuse (self-hosted / Cloud)    Analytics stack',
      '  ── REST / ClickHouse ──►          extractor',
      '                                    api          :8000',
      '                                    frontend     :8080',
      '                                    clickhouse   :8123 (analytics)',
      '                                      ▲ DATABASE_URL',
    ].join('\n'),
    commands: [
      'docker compose -f docker-compose.clickhouse.yml up -d --build',
      'docker compose -f docker-compose.clickhouse.yml run --rm api python seed_demo.py',
    ].join('\n'),
    notes: [
      'DATABASE_URL=clickhouse://default:chpass@clickhouse:8123/analytics is set by the compose file.',
      'Langfuse wiring in .env is unchanged.',
    ],
  },
  {
    name: 'Topology 4 — Langfuse Cloud + managed warehouse',
    tag: 'saas',
    when: 'No self-hosted database at all; Langfuse is Cloud; you want a managed, backed-up warehouse.',
    diagram: [
      'your host / serverless',
      '───────────────────────────────────────────────────────────',
      'Analytics stack                   Langfuse Cloud',
      '  extractor ── REST ────────────────►  cloud.langfuse.com',
      '  api          :8000',
      '  frontend     :8080',
      '      │',
      '      ▼ DATABASE_URL',
      'Managed warehouse',
      '  Neon / Supabase / RDS  (postgresql://)',
      '  or ClickHouse Cloud    (clickhouse://)',
    ].join('\n'),
    env: [
      'LANGFUSE_MODE=api',
      'LANGFUSE_BASE_URL=https://cloud.langfuse.com',
      'LANGFUSE_PROJECTS=\'[ … ]\'',
      'DATABASE_URL=postgresql://user:pass@your-db.neon.tech/analytics',
    ].join('\n'),
    notes: [
      'The "global / multi-team" path — no database to operate.',
      'Run extractor/api on any host or PaaS with DATABASE_URL overridden.',
    ],
  },
  {
    name: 'Topology 5 — Reuse Langfuse\u2019s own ClickHouse',
    tag: 'advanced',
    when: 'You already run Langfuse\u2019s ClickHouse and want zero extra warehouse infra.',
    diagram: [
      'one host',
      '───────────────────────────────────────────────────────────',
      'Langfuse (self-hosted)            Analytics stack',
      '  clickhouse :8123                  extractor',
      '    ├─ db "langfuse"   ◄── read ────┤ (LANGFUSE_MODE=clickhouse)',
      '    └─ db "analytics"  ◄── write ───┤ (DATABASE_URL)',
      '                                    api          :8000',
      '                                    frontend     :8080',
    ].join('\n'),
    env: [
      'LANGFUSE_MODE=clickhouse',
      'LANGFUSE_CLICKHOUSE_URL=http://host.docker.internal:8123',
      'DATABASE_URL=clickhouse://user:pass@host.docker.internal:8123/analytics',
    ].join('\n'),
    notes: [
      '\u2705 No second database to run; fastest ingestion (no API pagination).',
      '\u26a0 Couples the analytics warehouse to Langfuse\u2019s infra (contention, upgrade coupling).',
      '\u26a0 LANGFUSE_MODE=clickhouse reads Langfuse\u2019s column names, which vary by release — see extractor/clickhouse_client.py. The REST path is version-safe.',
    ],
  },
]

export const DECISION_TREE = [
  'Langfuse self-hosted or Cloud?',
  '\u251c\u2500\u2500 Self-hosted, one machine, small volume \u2026 Topology 1 (Postgres)',
  '\u2502     \u2514\u2500\u2500 large volume / long lookback \u2026\u2026 Topology 3 (ClickHouse)',
  '\u2502           \u2514\u2500\u2500 zero extra infra \u2026\u2026\u2026\u2026 Topology 5 (reuse Langfuse\u2019s CH)',
  '\u251c\u2500\u2500 Cloud, no self-hosted DB \u2026\u2026\u2026\u2026\u2026\u2026 Topology 4 (managed warehouse)',
  '\u2514\u2500\u2500 Laptop / CI / eval only \u2026\u2026\u2026\u2026\u2026\u2026 Topology 2 (DuckDB)',
].join('\n')
