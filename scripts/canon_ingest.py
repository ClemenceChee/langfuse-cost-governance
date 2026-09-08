"""Ingest canon governance exports into the configured warehouse.

    CANON_EXPORT_DIR=/path/to/exports \
    DATABASE_URL=duckdb://./dsh-analytics.duckdb python scripts/canon_ingest.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from warehouse import canonextract, get_warehouse

DSN = os.environ.get("DATABASE_URL", "duckdb://./dsh-analytics.duckdb")
EXPORT_DIR = os.environ.get("CANON_EXPORT_DIR", canonextract.CANON_EXPORT_DIR)


def main() -> None:
    warehouse = get_warehouse(DSN)
    n = canonextract.ingest(warehouse, root=EXPORT_DIR)
    print(f"Ingested {n} canon governance export(s).")


if __name__ == "__main__":
    main()
