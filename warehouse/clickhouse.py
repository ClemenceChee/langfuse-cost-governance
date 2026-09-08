import clickhouse_connect

from .base import Warehouse
from .dialects import CLICKHOUSE


class ClickHouseWarehouse(Warehouse):
    dialect = CLICKHOUSE

    def __init__(self, dsn, host, port, username, password, database):
        super().__init__(dsn)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password or "",
                database=self.database,
            )
        return self._client

    def query(self, sql_text: str, params=()):
        result = self._get_client().query(sql_text)
        return [dict(zip(result.column_names, row)) for row in result.result_rows]

    def execute(self, sql_text: str, params=()):
        self._get_client().command(sql_text)

    def executemany(self, sql_text: str, rows):
        raise NotImplementedError("ClickHouse uses native client.insert")

    def insert_native(self, table, columns, rows):
        if rows:
            self._get_client().insert(
                table, [list(r) for r in rows], column_names=columns
            )

    def truncate_table(self, table: str):
        self._get_client().command(f"TRUNCATE TABLE {table}")
