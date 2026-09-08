import time

import duckdb

from .base import Warehouse
from .dialects import DUCKDB


class DuckDBWarehouse(Warehouse):
    """Embedded single-file warehouse (zero-server). Good for local/dev use;
    DuckDB is single-writer, so use Postgres/ClickHouse for concurrent users."""

    dialect = DUCKDB

    def __init__(self, dsn: str, path: str):
        super().__init__(dsn)
        self.path = path

    def _conn(self, retries: int = 30, delay: float = 1.0):
        """Open a connection, retrying on the single-writer lock (the extractor
        and API can race at startup)."""
        last = None
        for _ in range(retries):
            try:
                return duckdb.connect(self.path)
            except Exception as e:  # duckdb.IOException for lock conflicts
                msg = str(e).lower()
                if "lock" not in msg and "io" not in msg:
                    raise
                last = e
                time.sleep(delay)
        raise last

    def query(self, sql_text: str, params=()):
        con = self._conn()
        try:
            cur = con.execute(sql_text, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            con.close()

    def execute(self, sql_text: str, params=()):
        con = self._conn()
        try:
            con.execute(sql_text, params)
        finally:
            con.close()

    def executemany(self, sql_text: str, rows):
        con = self._conn()
        try:
            # DuckDB autocommits per statement; a transaction batches them.
            con.execute("BEGIN TRANSACTION")
            try:
                con.executemany(sql_text, rows)
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        finally:
            con.close()

    def insert_native(self, table, columns, rows):
        raise NotImplementedError("DuckDB uses SQL upserts, not native insert")

    def truncate_table(self, table: str):
        self.execute(f"DELETE FROM {table}")
