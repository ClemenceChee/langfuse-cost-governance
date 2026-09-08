import psycopg
from psycopg.rows import dict_row

from .base import Warehouse
from .dialects import POSTGRES


class PostgresWarehouse(Warehouse):
    dialect = POSTGRES

    def query(self, sql_text: str, params=()):
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_text, params)
                return cur.fetchall()

    def execute(self, sql_text: str, params=()):
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_text, params)

    def executemany(self, sql_text: str, rows):
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.executemany(sql_text, rows)

    def insert_native(self, table, columns, rows):
        raise NotImplementedError("Postgres uses SQL upserts, not native insert")

    def truncate_table(self, table: str):
        self.execute(f"TRUNCATE {table}")
