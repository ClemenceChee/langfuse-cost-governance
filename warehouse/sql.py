"""The calculation layer, written once in terms of a `Dialect`.

Contains the normalized fact schema, the mart views (the derived KPIs), and the
KPI query strings. Backends in this package just execute these statements.
"""

# Canonical column order for fact rows (dicts from extractor/normalize.py).
FACT_COLUMNS = [
    "observation_id", "trace_id", "project_id", "project_name", "user_id",
    "session_id", "model", "type", "name", "environment", "start_time",
    "end_time", "latency_ms", "input_tokens", "output_tokens", "total_tokens",
    "cached_input_tokens", "reasoning_tokens", "input_cost", "output_cost",
    "total_cost", "level", "status_message", "tags",
]

# Canonical column order for Langfuse scores (evals).
FACT_SCORE_COLUMNS = [
    "score_id", "trace_id", "observation_id", "project_id", "project_name",
    "name", "value", "source", "timestamp",
]

# Canonical column order for canon governance exports (behaviour governance).
# `fact_governance` holds ONE ROW PER EXPORT SNAPSHOT (the aggregate metrics the
# canon `export --format json` document carries: ttrp, precision14, proposal
# queue counts). `dim_policy` is the ratified-policy registry and
# `fact_governance_divergence` the model x task-key divergence aggregate.
DIM_POLICY_COLUMNS = [
    "rule_key", "project_id", "kind", "status", "confidence",
    "promoted_at", "operator", "evidence_traces",
]

FACT_GOVERNANCE_COLUMNS = [
    "snapshot_id", "project_id", "exported_at", "ttrp_ms",
    "precision14_numerator", "precision14_denominator", "precision14_ratio",
    "proposals_total", "proposals_pending", "proposals_ratified",
    "proposals_rejected", "proposals_decayed",
]

FACT_GOVERNANCE_DIVERGENCE_COLUMNS = [
    "project_id", "model", "task_key", "divergent_traces", "total_traces",
]


def _create_table(d, name, cols, pk_cols, order_by, replacing=False):
    """cols: list of (column_name, type_key)."""
    lines = [f"{c} {getattr(d, tkey)}" for c, tkey in cols]
    pk = d.primary_key(", ".join(pk_cols))
    if pk:
        lines.append(pk)
    engine = d.table_engine(order_by, replacing)
    engine_clause = f" {engine}" if engine else ""
    body = ",\n    ".join(lines)
    return f"CREATE TABLE IF NOT EXISTS {name} (\n    {body}\n){engine_clause}"


def _fact_table(d):
    return _create_table(
        d,
        "fact_observation",
        [
            ("observation_id", "text"),
            ("trace_id", "text"),
            ("project_id", "text"),
            ("project_name", "text"),
            ("user_id", "text"),
            ("session_id", "text"),
            ("model", "text"),
            ("type", "text"),
            ("name", "text"),
            ("environment", "text"),
            ("start_time", "ts"),
            ("end_time", "ts"),
            ("latency_ms", "double"),
            ("input_tokens", "bigint"),
            ("output_tokens", "bigint"),
            ("total_tokens", "bigint"),
            ("cached_input_tokens", "bigint"),
            ("reasoning_tokens", "bigint"),
            ("input_cost", "double"),
            ("output_cost", "double"),
            ("total_cost", "double"),
            ("level", "text"),
            ("status_message", "text"),
            ("tags", "text"),
        ],
        pk_cols=["observation_id"],
        order_by="observation_id",
        replacing=True,
    )


def _score_table(d):
    return _create_table(
        d,
        "fact_score",
        [
            ("score_id", "text"),
            ("trace_id", "text"),
            ("observation_id", "text"),
            ("project_id", "text"),
            ("project_name", "text"),
            ("name", "text"),
            ("value", "double"),
            ("source", "text"),
            ("timestamp", "ts"),
        ],
        pk_cols=["score_id"],
        order_by="score_id",
        replacing=True,
    )


def schema_statements(d) -> list[str]:
    stmts = [
        _fact_table(d),
        _score_table(d),
        _create_table(
            d, "dim_user",
            [
                ("user_id", "text"),
                ("display_name", "text"),
                ("team", "text"),
                ("department", "text"),
            ],
            pk_cols=["user_id"], order_by="user_id", replacing=True,
        ),
        _create_table(
            d, "budget",
            [
                ("scope_type", "text"),
                ("scope_id", "text"),
                ("period", "text"),
                ("budget_usd", "double"),
            ],
            pk_cols=["scope_type", "scope_id", "period"],
            order_by="scope_type, scope_id, period",
        ),
        _create_table(
            d, "model_prices",
            [
                ("model", "text"),
                ("input_hit_per_1m", "double"),
                ("input_miss_per_1m", "double"),
                ("output_per_1m", "double"),
            ],
            pk_cols=["model"],
            order_by="model",
        ),
        _create_table(
            d, "targets",
            [
                ("metric", "text"),
                ("op", "text"),
                ("threshold", "double"),
                ("label", "text"),
            ],
            pk_cols=["metric"],
            order_by="metric",
        ),
        _create_table(
            d, "sync_state",
            [
                ("key", "text"),
                ("value", "text"),
                ("updated_at", "ts"),
            ],
            pk_cols=["key"], order_by="key", replacing=True,
        ),
        # --- behaviour governance (canon export -> dashboard ingest) ---
        _create_table(
            d, "dim_policy",
            [
                ("rule_key", "text"),
                ("project_id", "text"),
                ("kind", "text"),
                ("status", "text"),
                ("confidence", "double"),
                ("promoted_at", "ts"),
                ("operator", "text"),
                ("evidence_traces", "bigint"),
            ],
            pk_cols=["rule_key"], order_by="rule_key", replacing=True,
        ),
        _create_table(
            d, "fact_governance",
            [
                ("snapshot_id", "text"),
                ("project_id", "text"),
                ("exported_at", "ts"),
                ("ttrp_ms", "double"),
                ("precision14_numerator", "bigint"),
                ("precision14_denominator", "bigint"),
                ("precision14_ratio", "double"),
                ("proposals_total", "bigint"),
                ("proposals_pending", "bigint"),
                ("proposals_ratified", "bigint"),
                ("proposals_rejected", "bigint"),
                ("proposals_decayed", "bigint"),
            ],
            pk_cols=["snapshot_id"], order_by="snapshot_id", replacing=True,
        ),
        _create_table(
            d, "fact_governance_divergence",
            [
                ("project_id", "text"),
                ("model", "text"),
                ("task_key", "text"),
                ("divergent_traces", "bigint"),
                ("total_traces", "bigint"),
            ],
            pk_cols=["project_id", "model", "task_key"],
            order_by="project_id, model, task_key", replacing=True,
        ),
    ]
    if d.supports_indexes:
        for col in ("start_time", "project_id", "user_id", "model"):
            stmts.append(
                f"CREATE INDEX IF NOT EXISTS idx_obs_{col} "
                f"ON fact_observation ({col})"
            )
    return stmts


def migration_statements(d) -> list[str]:
    """Idempotent, backward-compatible column additions (no-op on fresh DBs)."""
    if d.name == "postgres":
        return [
            "ALTER TABLE fact_observation "
            "ADD COLUMN IF NOT EXISTS session_id TEXT"
        ]
    if d.name == "duckdb":
        return [
            "ALTER TABLE fact_observation "
            "ADD COLUMN IF NOT EXISTS session_id VARCHAR"
        ]
    if d.name == "clickhouse":
        return [
            "ALTER TABLE fact_observation "
            "ADD COLUMN IF NOT EXISTS session_id Nullable(String)"
        ]
    return []


# Every mart view, so ensure_schema can drop them before (re)create. Dropping
# first matters: CREATE OR REPLACE VIEW cannot change an existing view's column
# names/order, so schema evolution would otherwise fail with
# "cannot change name of view column".
VIEW_NAMES = [
    "mrt_daily_usage",
    "mrt_model_efficiency",
    "mrt_org_daily",
    "mrt_session",
    "mrt_model_daily",
    "mrt_hourly_usage",
    "mrt_governance_daily",
    "mrt_policy_coverage",
]


def drop_view_statements(d) -> list[str]:
    cascade = " CASCADE" if d.name == "postgres" else ""
    return [f"DROP VIEW IF EXISTS {name}{cascade}" for name in VIEW_NAMES]


def view_statements(d) -> list[str]:
    fact = d.table_ref("fact_observation")
    fact_f = d.table_ref("fact_observation", "f")
    users_u = d.table_ref("dim_user", "u")
    return [
        # Daily grain: project x team x user x model x day.
        f"""
CREATE OR REPLACE VIEW mrt_daily_usage AS
SELECT
    {d.day_bucket('f.start_time')}                  AS day,
    COALESCE(f.project_id, '(unknown)')             AS project_id,
    COALESCE(f.project_name, f.project_id, '(unknown)') AS project_name,
    COALESCE(f.user_id, '(unattributed)')           AS user_id,
    COALESCE({d.nullif('u.team', "''")}, 'Unassigned') AS team,
    COALESCE(f.model, '(unknown)')                  AS model,
    COUNT(*)                                        AS observations,
    {d.distinct_count('f.trace_id')}                AS traces,
    {d.int_cast('SUM(f.input_tokens)')}             AS input_tokens,
    {d.int_cast('SUM(f.output_tokens)')}            AS output_tokens,
    {d.int_cast('SUM(f.total_tokens)')}             AS total_tokens,
    {d.int_cast('SUM(f.cached_input_tokens)')}      AS cached_input_tokens,
    {d.int_cast('SUM(f.reasoning_tokens)')}         AS reasoning_tokens,
    SUM(f.input_cost)                               AS input_cost,
    SUM(f.output_cost)                              AS output_cost,
    SUM(f.total_cost)                               AS total_cost
FROM {fact_f}
LEFT JOIN {users_u} ON u.user_id = f.user_id
GROUP BY 1, 2, 3, 4, 5, 6
""",
        # Model-level efficiency KPIs. A subquery is used so the ratio columns
        # operate on already-aggregated values (ClickHouse lets a SELECT alias
        # shadow the raw column, which would otherwise turn SUM(x) into
        # SUM(SUM(x)) when the alias matches the raw column name).
        f"""
CREATE OR REPLACE VIEW mrt_model_efficiency AS
SELECT
    model,
    input_tokens,
    output_tokens,
    cached_input_tokens,
    reasoning_tokens,
    total_cost,
    {d.ratio('cached_input_tokens', 'input_tokens', 4)}  AS cache_hit_rate,
    {d.ratio('reasoning_tokens', 'total_tokens', 4)}     AS reasoning_share,
    {d.ratio('output_tokens', 'input_tokens', 4)}        AS output_input_ratio,
    {d.ratio('total_cost * 1000.0', 'total_tokens', 6)}  AS cost_per_1k_tokens,
    {d.round('avg_latency_ms', 1)}                       AS avg_latency_ms
FROM (
    SELECT
        COALESCE(model, '(unknown)')                     AS model,
        {d.int_cast('SUM(input_tokens)')}                AS input_tokens,
        {d.int_cast('SUM(output_tokens)')}               AS output_tokens,
        {d.int_cast('SUM(cached_input_tokens)')}         AS cached_input_tokens,
        {d.int_cast('SUM(reasoning_tokens)')}            AS reasoning_tokens,
        {d.int_cast('SUM(total_tokens)')}                AS total_tokens,
        SUM(total_cost)                                  AS total_cost,
        AVG(latency_ms)                                  AS avg_latency_ms
    FROM {fact}
    GROUP BY 1
) AS m
""",
        # Whole-org daily roll-up.
        f"""
CREATE OR REPLACE VIEW mrt_org_daily AS
SELECT
    day,
    {d.int_cast('SUM(observations)')}    AS observations,
    {d.int_cast('SUM(traces)')}          AS traces,
    {d.int_cast('SUM(input_tokens)')}    AS input_tokens,
    {d.int_cast('SUM(output_tokens)')}   AS output_tokens,
    {d.int_cast('SUM(total_tokens)')}    AS total_tokens,
    {d.int_cast('SUM(cached_input_tokens)')} AS cached_input_tokens,
    {d.int_cast('SUM(reasoning_tokens)')} AS reasoning_tokens,
    SUM(total_cost)                      AS total_cost
FROM mrt_daily_usage
GROUP BY 1
""",
        # Session grain: context & turns per session (multi-turn agent/chat).
        f"""
CREATE OR REPLACE VIEW mrt_session AS
SELECT
    COALESCE(f.session_id, f.trace_id)              AS session_id,
    COALESCE(f.user_id, '(unattributed)')           AS user_id,
    COALESCE(f.project_name, f.project_id, '(unknown)') AS project_name,
    MIN(f.start_time)                               AS first_seen,
    MAX(f.start_time)                               AS last_seen,
    {d.distinct_count('f.trace_id')}                AS turns,
    COUNT(*)                                        AS observations,
    {d.int_cast('SUM(f.input_tokens)')}             AS input_tokens,
    {d.int_cast('SUM(f.output_tokens)')}            AS output_tokens,
    {d.int_cast('SUM(f.total_tokens)')}             AS total_tokens,
    SUM(f.total_cost)                               AS total_cost
FROM {fact_f}
GROUP BY 1, 2, 3
""",
        # Per-model efficiency AS A TIME SERIES (leading indicators with a trend).
        f"""
CREATE OR REPLACE VIEW mrt_model_daily AS
SELECT
    day, model, input_tokens, output_tokens, cached_input_tokens,
    reasoning_tokens, total_tokens, total_cost, avg_latency_ms,
    {d.ratio('cached_input_tokens', 'input_tokens', 4)}  AS cache_hit_rate,
    {d.ratio('reasoning_tokens', 'total_tokens', 4)}     AS reasoning_share,
    {d.ratio('output_tokens', 'input_tokens', 4)}        AS output_input_ratio,
    {d.ratio('total_cost * 1000.0', 'total_tokens', 6)}  AS cost_per_1k_tokens
FROM (
    SELECT
        {d.day_bucket('start_time')}                     AS day,
        COALESCE(model, '(unknown)')                     AS model,
        {d.int_cast('SUM(input_tokens)')}                AS input_tokens,
        {d.int_cast('SUM(output_tokens)')}               AS output_tokens,
        {d.int_cast('SUM(cached_input_tokens)')}         AS cached_input_tokens,
        {d.int_cast('SUM(reasoning_tokens)')}            AS reasoning_tokens,
        {d.int_cast('SUM(total_tokens)')}                AS total_tokens,
        SUM(total_cost)                                  AS total_cost,
        AVG(latency_ms)                                  AS avg_latency_ms
    FROM {fact}
    GROUP BY 1, 2
) AS m
""",
        # Hourly grain for intra-day spikes and heatmaps.
        f"""
CREATE OR REPLACE VIEW mrt_hourly_usage AS
SELECT
    {d.hour_bucket('f.start_time')}                     AS hour,
    COALESCE(f.project_name, f.project_id, '(unknown)') AS project_name,
    COUNT(*)                                            AS observations,
    {d.int_cast('SUM(f.input_tokens)')}                 AS input_tokens,
    {d.int_cast('SUM(f.output_tokens)')}                AS output_tokens,
    {d.int_cast('SUM(f.total_tokens)')}                 AS total_tokens,
    SUM(f.total_cost)                                   AS total_cost
FROM {fact_f}
GROUP BY 1, 2
""",
        # Behaviour governance: the LATEST canon export snapshot per day
        # (snapshots accumulate per poll; ROW_NUMBER keeps only the most recent
        # per day) — proposals/ratifications over time.
        f"""
CREATE OR REPLACE VIEW mrt_governance_daily AS
SELECT
    day,
    ttrp_ms,
    precision14_ratio,
    proposals_total,
    proposals_pending,
    proposals_ratified,
    proposals_rejected,
    proposals_decayed
FROM (
    SELECT
        {d.day_bucket('g.exported_at')} AS day,
        g.ttrp_ms,
        g.precision14_ratio,
        g.proposals_total,
        g.proposals_pending,
        g.proposals_ratified,
        g.proposals_rejected,
        g.proposals_decayed,
        ROW_NUMBER() OVER (
            PARTITION BY {d.day_bucket('g.exported_at')}
            ORDER BY g.exported_at DESC
        ) AS rn
    FROM {d.table_ref('fact_governance', 'g')}
) AS t
WHERE t.rn = 1
""",
        # Behaviour governance: share of traces covered by ratified policy
        # evidence. `evidence_traces` is a per-policy distinct-trace count (the
        # canon export carries counts, not trace ids), so this is an upper
        # bound with multiplicity; coverage_ratio is null while no traces exist.
        f"""
CREATE OR REPLACE VIEW mrt_policy_coverage AS
SELECT
    ratified_policies,
    evidence_traces,
    total_traces,
    {d.ratio('evidence_traces', 'total_traces', 4)} AS coverage_ratio
FROM (
    SELECT
        (SELECT {d.int_cast('COUNT(*)')} FROM {d.table_ref('dim_policy')}) AS ratified_policies,
        (SELECT {d.int_cast('COALESCE(SUM(evidence_traces), 0)')} FROM {d.table_ref('dim_policy')}) AS evidence_traces,
        (SELECT {d.distinct_count('trace_id')} FROM {d.table_ref('fact_observation')}) AS total_traces
) AS t
""",
    ]


# ---------------------------------------------------------------------------
# Write-path statements (Postgres / DuckDB; ClickHouse uses native inserts).
# ---------------------------------------------------------------------------

def upsert_statement(d) -> str | None:
    cols = ", ".join(FACT_COLUMNS)
    ph = ", ".join([d.placeholder()] * len(FACT_COLUMNS))
    if d.name == "postgres":
        updates = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in FACT_COLUMNS if c != "observation_id"
        )
        return (
            f"INSERT INTO fact_observation ({cols}) VALUES ({ph}) "
            f"ON CONFLICT (observation_id) DO UPDATE SET {updates}"
        )
    if d.name == "duckdb":
        return f"INSERT OR REPLACE INTO fact_observation ({cols}) VALUES ({ph})"
    return None


def upsert_score_statement(d) -> str | None:
    cols = ", ".join(FACT_SCORE_COLUMNS)
    ph = ", ".join([d.placeholder()] * len(FACT_SCORE_COLUMNS))
    if d.name == "postgres":
        updates = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in FACT_SCORE_COLUMNS if c != "score_id"
        )
        return (
            f"INSERT INTO fact_score ({cols}) VALUES ({ph}) "
            f"ON CONFLICT (score_id) DO UPDATE SET {updates}"
        )
    if d.name == "duckdb":
        return f"INSERT OR REPLACE INTO fact_score ({cols}) VALUES ({ph})"
    return None


def upsert_policy_statement(d) -> str | None:
    cols = ", ".join(DIM_POLICY_COLUMNS)
    ph = ", ".join([d.placeholder()] * len(DIM_POLICY_COLUMNS))
    if d.name == "postgres":
        updates = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in DIM_POLICY_COLUMNS if c != "rule_key"
        )
        return (
            f"INSERT INTO dim_policy ({cols}) VALUES ({ph}) "
            f"ON CONFLICT (rule_key) DO UPDATE SET {updates}"
        )
    if d.name == "duckdb":
        return f"INSERT OR REPLACE INTO dim_policy ({cols}) VALUES ({ph})"
    return None


def upsert_governance_statement(d) -> str | None:
    cols = ", ".join(FACT_GOVERNANCE_COLUMNS)
    ph = ", ".join([d.placeholder()] * len(FACT_GOVERNANCE_COLUMNS))
    if d.name == "postgres":
        updates = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in FACT_GOVERNANCE_COLUMNS if c != "snapshot_id"
        )
        return (
            f"INSERT INTO fact_governance ({cols}) VALUES ({ph}) "
            f"ON CONFLICT (snapshot_id) DO UPDATE SET {updates}"
        )
    if d.name == "duckdb":
        return f"INSERT OR REPLACE INTO fact_governance ({cols}) VALUES ({ph})"
    return None


def upsert_governance_divergence_statement(d) -> str | None:
    cols = ", ".join(FACT_GOVERNANCE_DIVERGENCE_COLUMNS)
    ph = ", ".join([d.placeholder()] * len(FACT_GOVERNANCE_DIVERGENCE_COLUMNS))
    if d.name == "postgres":
        updates = ", ".join(
            f"{c} = EXCLUDED.{c}"
            for c in FACT_GOVERNANCE_DIVERGENCE_COLUMNS
            if c not in ("project_id", "model", "task_key")
        )
        return (
            f"INSERT INTO fact_governance_divergence ({cols}) VALUES ({ph}) "
            f"ON CONFLICT (project_id, model, task_key) DO UPDATE SET {updates}"
        )
    if d.name == "duckdb":
        return f"INSERT OR REPLACE INTO fact_governance_divergence ({cols}) VALUES ({ph})"
    return None


def dim_user_ignore_statement(d) -> str | None:
    if d.name == "postgres":
        return "INSERT INTO dim_user (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING"
    if d.name == "duckdb":
        return "INSERT OR IGNORE INTO dim_user (user_id) VALUES (?)"
    return None


def sync_upsert_statement(d) -> str | None:
    if d.name == "postgres":
        return (
            "INSERT INTO sync_state (key, value, updated_at) "
            "VALUES ('last_sync_at', %s, now()) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"
        )
    if d.name == "duckdb":
        return (
            "INSERT OR REPLACE INTO sync_state (key, value, updated_at) "
            "VALUES ('last_sync_at', ?, now())"
        )
    return None


def bulk_insert_statement(d, table: str, columns: list[str]) -> str | None:
    if d.name == "clickhouse":
        return None  # native client.insert path
    cols = ", ".join(columns)
    ph = ", ".join([d.placeholder()] * len(columns))
    return f"INSERT INTO {table} ({cols}) VALUES ({ph})"


# ---------------------------------------------------------------------------
# KPI queries.
# ---------------------------------------------------------------------------

def kpi_overview_mtd(d) -> str:
    return f"""
SELECT
    {d.float_cast('SUM(total_cost)')}            AS cost_mtd,
    {d.int_cast('SUM(total_tokens)')}            AS tokens_mtd,
    {d.int_cast('SUM(input_tokens)')}            AS input_tokens_mtd,
    {d.int_cast('SUM(output_tokens)')}           AS output_tokens_mtd,
    {d.int_cast('SUM(cached_input_tokens)')}     AS cached_tokens_mtd,
    COUNT(*)                                     AS observations_mtd,
    {d.distinct_count('user_id')}                AS active_users_mtd,
    {d.distinct_count('session_id')}             AS sessions_mtd,
    COALESCE({d.ratio('SUM(total_cost) * 1000.0', 'SUM(total_tokens)', 6)}, 0) AS cost_per_1k_tokens
FROM {d.table_ref('fact_observation')}
WHERE start_time >= {d.month_start('now()')}
"""


def kpi_overview_wow(d) -> str:
    last7 = d.sum_if("total_cost", f"start_time >= {d.now_minus_days(7)}")
    prev7 = d.sum_if(
        "total_cost",
        f"start_time >= {d.now_minus_days(14)} AND start_time < {d.now_minus_days(7)}",
    )
    return f"""
SELECT
    COALESCE({last7}, 0) AS last7,
    COALESCE({prev7}, 0) AS prev7
FROM {d.table_ref('fact_observation')}
"""


def kpi_daily(d, col: str, days: int) -> str:
    # `day` is selected raw (a Date); base.daily() serializes it to a string.
    return f"""
SELECT
    day        AS day,
    {col}      AS label,
    {d.float_cast('SUM(total_cost)')}   AS total_cost,
    {d.int_cast('SUM(total_tokens)')}   AS total_tokens,
    {d.int_cast('SUM(observations)')}   AS observations
FROM mrt_daily_usage
WHERE day >= {d.days_ago_date(days)}
GROUP BY day, {col}
ORDER BY day, {col}
"""


def kpi_top(d, col: str, metric_col: str, days: int, limit: int) -> str:
    return f"""
SELECT
    {col}                     AS label,
    {d.float_cast('SUM(total_cost)')}   AS total_cost,
    {d.int_cast('SUM(total_tokens)')}   AS total_tokens,
    {d.int_cast('SUM(observations)')}   AS observations
FROM mrt_daily_usage
WHERE day >= {d.days_ago_date(days)}
GROUP BY {col}
ORDER BY {metric_col} DESC
LIMIT {limit}
"""


def kpi_efficiency(d) -> str:
    return f"""
SELECT
    model,
    input_tokens,
    output_tokens,
    cached_input_tokens,
    reasoning_tokens,
    total_cost,
    cache_hit_rate,
    reasoning_share,
    output_input_ratio,
    cost_per_1k_tokens,
    avg_latency_ms
FROM mrt_model_efficiency
ORDER BY total_cost DESC
"""


def kpi_governance_budget(d) -> str:
    return (
        "SELECT budget_usd FROM budget "
        "WHERE scope_type = 'global' AND scope_id = '*' AND period = 'monthly'"
    )


def kpi_governance_mtd(d) -> str:
    return f"""
SELECT
    {d.float_cast('COALESCE(SUM(total_cost), 0)')} AS mtd_cost,
    {d.distinct_count('user_id')}     AS active_users
FROM {d.table_ref('fact_observation')}
WHERE start_time >= {d.month_start('now()')}
"""


def kpi_governance_unattributed(d) -> str:
    return f"""
SELECT {d.float_cast('COALESCE(SUM(total_cost), 0)')} AS cost
FROM mrt_daily_usage
WHERE team = 'Unassigned'
  AND day >= {d.month_start_date()}
"""


def kpi_session_stats(d, days: int) -> str:
    return f"""
SELECT
    COUNT(*)                                    AS sessions,
    {d.round('AVG(input_tokens)', 1)}           AS avg_context_tokens,
    {d.round('AVG(turns)', 1)}                  AS avg_turns,
    {d.round('AVG(total_cost)', 4)}             AS avg_cost,
    {d.ratio('SUM(input_tokens)', 'SUM(turns)', 1)} AS avg_input_per_turn
FROM mrt_session
WHERE last_seen >= {d.now_minus_days(days)}
"""


def kpi_sessions_top(d, days: int, limit: int) -> str:
    return f"""
SELECT
    session_id,
    user_id,
    project_name,
    turns,
    observations,
    input_tokens,
    output_tokens,
    total_cost,
    {d.ratio('input_tokens', 'turns', 1)} AS input_per_turn
FROM mrt_session
WHERE last_seen >= {d.now_minus_days(days)}
ORDER BY input_tokens DESC
LIMIT {limit}
"""


def kpi_concentration(d, days: int, n: int) -> str:
    return f"""
SELECT {d.float_cast('SUM(total_cost)')} AS top_cost
FROM (
    SELECT SUM(total_cost) AS total_cost
    FROM mrt_daily_usage
    WHERE day >= {d.days_ago_date(days)}
    GROUP BY user_id
    ORDER BY total_cost DESC
    LIMIT {n}
) t
"""


def kpi_total_days_cost(d, days: int) -> str:
    return f"""
SELECT {d.float_cast('SUM(total_cost)')} AS total_cost
FROM mrt_daily_usage
WHERE day >= {d.days_ago_date(days)}
"""


def kpi_org_daily(d, days: int) -> str:
    return f"""
SELECT day, total_cost
FROM mrt_org_daily
WHERE day >= {d.days_ago_date(days)}
ORDER BY day
"""


def kpi_trace_outcomes(d, score_name: str | None) -> str:
    obs = d.table_ref("fact_observation", "o")
    scores = d.table_ref("fact_score", "sc")
    name_filter = f"WHERE sc.name = '{score_name}'" if score_name else ""
    return f"""
SELECT tc.trace_id AS trace_id, tc.cost AS cost, s.best_score AS best_score
FROM (
    SELECT o.trace_id AS trace_id, {d.float_cast('COALESCE(SUM(o.total_cost), 0)')} AS cost
    FROM {obs}
    GROUP BY o.trace_id
) tc
JOIN (
    SELECT sc.trace_id AS trace_id, MAX(sc.value) AS best_score
    FROM {scores}
    {name_filter}
    GROUP BY sc.trace_id
) s ON s.trace_id = tc.trace_id
"""


def kpi_model_daily(d, days: int, model: str | None) -> str:
    conds = [f"day >= {d.days_ago_date(days)}"]
    if model:
        conds.append(f"model = '{model}'")
    clause = "WHERE " + " AND ".join(conds)
    return f"""
SELECT
    day, model, cache_hit_rate, reasoning_share, output_input_ratio,
    cost_per_1k_tokens, input_tokens, output_tokens, total_cost
FROM mrt_model_daily
{clause}
ORDER BY day, model
"""


def kpi_hourly(d, days: int, project: str | None) -> str:
    conds = [f"hour >= {d.now_minus_days(days)}"]
    if project:
        conds.append(f"project_name = '{project}'")
    clause = "WHERE " + " AND ".join(conds)
    return f"""
SELECT hour, project_name, observations, input_tokens, output_tokens, total_tokens, total_cost
FROM mrt_hourly_usage
{clause}
ORDER BY hour, project_name
"""


def kpi_user_daily(d, days: int) -> str:
    return f"""
SELECT user_id, day, {d.float_cast('SUM(total_cost)')} AS total_cost
FROM mrt_daily_usage
WHERE day >= {d.days_ago_date(days)}
GROUP BY user_id, day
ORDER BY day, user_id
"""


# ---------------------------------------------------------------------------
# Behaviour governance (canon export -> warehouse) queries.
# ---------------------------------------------------------------------------

def kpi_governance_snapshot(d) -> str:
    """The most recent canon export snapshot's metrics (latest by exported_at)."""
    return f"""
SELECT
    ttrp_ms,
    precision14_numerator,
    precision14_denominator,
    precision14_ratio,
    proposals_total,
    proposals_pending,
    proposals_ratified,
    proposals_rejected,
    proposals_decayed
FROM {d.table_ref('fact_governance')}
ORDER BY exported_at DESC
LIMIT 1
"""


def kpi_governance_policies(d) -> str:
    return f"""
SELECT rule_key, project_id, kind, status, confidence, promoted_at, operator, evidence_traces
FROM {d.table_ref('dim_policy')}
ORDER BY rule_key
"""


def kpi_governance_divergence(d) -> str:
    return f"""
SELECT project_id, model, task_key, divergent_traces, total_traces
FROM {d.table_ref('fact_governance_divergence')}
ORDER BY model, task_key
"""
