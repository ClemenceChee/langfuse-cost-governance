"""SQL dialects.

Every backend-specific SQL quirk is captured here so the calculation layer in
`sql.py` stays written once. To add a new warehouse, subclass `Dialect` and
register it in `warehouse/__init__.py`.
"""


class Dialect:
    name = "postgres"
    text = "TEXT"
    bigint = "BIGINT"
    double = "DOUBLE PRECISION"
    ts = "TIMESTAMPTZ"
    supports_indexes = False
    register_users_lazily = True

    def placeholder(self) -> str:
        return "%s"

    def int_cast(self, e: str) -> str:
        return f"({e})::bigint"

    def float_cast(self, e: str) -> str:
        return f"({e})::float8"

    def round(self, e: str, n: int) -> str:
        return f"ROUND(({e})::numeric, {n})::float8"

    def ratio(self, a: str, b: str, n: int) -> str:
        return f"ROUND(({a})::numeric / NULLIF(({b}), 0)::numeric, {n})::float8"

    def day_bucket(self, e: str) -> str:
        return f"date_trunc('day', {e} AT TIME ZONE 'UTC')::date"

    def hour_bucket(self, e: str) -> str:
        return f"date_trunc('hour', {e} AT TIME ZONE 'UTC')"

    def month_start(self, e: str) -> str:
        return f"date_trunc('month', {e})"

    def month_start_date(self) -> str:
        return "date_trunc('month', now())::date"

    def now_minus_days(self, n: int) -> str:
        return f"now() - interval '{n} days'"

    def days_ago_date(self, n: int) -> str:
        return f"(CURRENT_DATE - {n})"

    def distinct_count(self, e: str) -> str:
        return f"COUNT(DISTINCT {e})"

    def sum_if(self, e: str, cond: str) -> str:
        return f"SUM({e}) FILTER (WHERE {cond})"

    def nullif(self, a: str, b: str) -> str:
        return f"NULLIF({a}, {b})"

    def day_to_string(self, col: str) -> str:
        return f"to_char({col}, 'YYYY-MM-DD')"

    def table_ref(self, name: str, alias: str | None = None) -> str:
        return f"{name} AS {alias}" if alias else name

    def primary_key(self, cols: str) -> str:
        return f"PRIMARY KEY ({cols})"

    def table_engine(self, order_by: str, replacing: bool = False) -> str:
        return ""


POSTGRES = Dialect()
POSTGRES.name = "postgres"
POSTGRES.supports_indexes = True


class _DuckDB(Dialect):
    name = "duckdb"
    text = "VARCHAR"
    double = "DOUBLE"

    def placeholder(self) -> str:
        return "?"

    def int_cast(self, e: str) -> str:
        return f"({e})::BIGINT"

    def float_cast(self, e: str) -> str:
        return f"({e})::DOUBLE"

    def round(self, e: str, n: int) -> str:
        return f"ROUND({e}, {n})"

    def ratio(self, a: str, b: str, n: int) -> str:
        return f"ROUND(({a})::DOUBLE / NULLIF(({b}), 0)::DOUBLE, {n})"

    def day_bucket(self, e: str) -> str:
        return f"date_trunc('day', {e})::DATE"

    def hour_bucket(self, e: str) -> str:
        return f"date_trunc('hour', {e})"

    def month_start_date(self) -> str:
        return "date_trunc('month', now())::DATE"

    def now_minus_days(self, n: int) -> str:
        return f"now() - INTERVAL {n} DAY"

    def day_to_string(self, col: str) -> str:
        return f"CAST({col} AS VARCHAR)"


DUCKDB = _DuckDB()


class _ClickHouse(Dialect):
    name = "clickhouse"
    text = "Nullable(String)"
    bigint = "Int64"
    double = "Nullable(Float64)"
    ts = "Nullable(DateTime64(3, 'UTC'))"
    # Lazy INSERT would clobber manually-set teams (ReplacingMergeTree keeps the
    # latest row), so unassigned users simply have no dim_user row -> 'Unassigned'.
    register_users_lazily = False

    def placeholder(self) -> str:
        # ClickHouse writes use the native client.insert path, not SQL params.
        return ""

    def int_cast(self, e: str) -> str:
        # SUM(Int64) already returns Int64; wrapping it in toInt64 alongside a
        # toFloat64(...) of the same column trips ClickHouse's aggregate analyzer.
        return e

    def float_cast(self, e: str) -> str:
        return e

    def round(self, e: str, n: int) -> str:
        return f"round({e}, {n})"

    def ratio(self, a: str, b: str, n: int) -> str:
        return f"round({a} / nullIf({b}, 0), {n})"

    def day_bucket(self, e: str) -> str:
        return f"toDate({e})"

    def hour_bucket(self, e: str) -> str:
        return f"toStartOfHour({e})"

    def month_start(self, e: str) -> str:
        return f"toStartOfMonth({e})"

    def month_start_date(self) -> str:
        return "toDate(toStartOfMonth(now()))"

    def now_minus_days(self, n: int) -> str:
        return f"now() - INTERVAL {n} DAY"

    def days_ago_date(self, n: int) -> str:
        return f"(today() - {n})"

    def distinct_count(self, e: str) -> str:
        # COUNT(DISTINCT ...) excludes NULLs in PG/DuckDB; uniqExact counts them,
        # so filter NULLs to match (avoids +1 skew on user/session counts).
        return f"uniqExactIf({e}, isNotNull({e}))"

    def sum_if(self, e: str, cond: str) -> str:
        return f"sumIf({e}, {cond})"

    def nullif(self, a: str, b: str) -> str:
        return f"nullIf({a}, {b})"

    def day_to_string(self, col: str) -> str:
        return f"toString({col})"

    def table_ref(self, name: str, alias: str | None = None) -> str:
        # ReplacingMergeTree dedups on read via FINAL; alias precedes FINAL.
        return f"{name} AS {alias} FINAL" if alias else f"{name} FINAL"

    def primary_key(self, cols: str) -> str:
        return ""

    def table_engine(self, order_by: str, replacing: bool = False) -> str:
        engine = "ReplacingMergeTree()" if replacing else "MergeTree()"
        return f"ENGINE = {engine} ORDER BY ({order_by}) SETTINGS allow_nullable_key = 1"


CLICKHOUSE = _ClickHouse()
