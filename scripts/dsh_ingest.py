"""Ingest DSH session logs into the configured warehouse.

    DATABASE_URL=duckdb://./dsh-analytics.duckdb python scripts/dsh_ingest.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from warehouse import dshextract, get_warehouse

DSN = os.environ.get("DATABASE_URL", "duckdb://./dsh-analytics.duckdb")


def main() -> None:
    warehouse = get_warehouse(DSN)
    n = dshextract.ingest(warehouse)
    print(f"Ingested {n} observations from DSH sessions.")


if __name__ == "__main__":
    main()
