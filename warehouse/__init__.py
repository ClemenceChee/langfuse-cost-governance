"""Warehouse factory.

Pick the analytics warehouse with a URL (SQLAlchemy-style):
    postgres://user:pass@host:5432/db          -> Postgres (server)
    duckdb:///path/to/analytics.duckdb         -> DuckDB (embedded, zero-server)
    clickhouse://user:pass@host:8123/db        -> ClickHouse (server)
"""
import os
from urllib.parse import unquote, urlparse


def get_warehouse(database_url: str):
    scheme = database_url.split("://", 1)[0].lower() if "://" in database_url else ""

    if scheme in ("postgres", "postgresql"):
        from .postgres import PostgresWarehouse
        return PostgresWarehouse(database_url)

    if scheme == "duckdb":
        from .duckdb import DuckDBWarehouse
        rest = database_url[len("duckdb://"):]
        if rest in (":memory:", "/:memory:"):
            return DuckDBWarehouse(database_url, ":memory:")
        path = unquote(rest)
        if path.startswith("/"):
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        else:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        return DuckDBWarehouse(database_url, path)

    if scheme in ("clickhouse", "clickhouses"):
        from .clickhouse import ClickHouseWarehouse
        p = urlparse(database_url)
        return ClickHouseWarehouse(
            database_url,
            host=p.hostname or "localhost",
            port=p.port or 8123,
            username=p.username or "default",
            password=p.password or "",
            database=(p.path or "/default").lstrip("/") or "default",
        )

    raise ValueError(f"Unsupported DATABASE_URL scheme: {scheme!r}")
