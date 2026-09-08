"""Ingest canon governance exports on an interval (sidecar loop).

Run as a service (see docker-compose.grafana.yml `canon-ingest`) or directly:

    CANON_EXPORT_DIR=/path/to/exports \
    DATABASE_URL=postgresql://... \
    python canon_ingest_loop.py

The ingest is an idempotent upsert keyed on stable ids (snapshot_id for the
metrics snapshot, rule_key for policies, project/model/task_key for
divergence), so re-runs add new exports without duplicating rows.
"""
import os
import time
import traceback

from warehouse import canonextract, get_warehouse

DSN = os.getenv(
    "DATABASE_URL", "postgresql://analytics:analytics@postgres:5432/analytics"
)
INTERVAL = int(os.getenv("CANON_INGEST_INTERVAL_SECONDS", "300"))
EXPORT_DIR = os.getenv("CANON_EXPORT_DIR", canonextract.CANON_EXPORT_DIR)


def main() -> None:
    warehouse = get_warehouse(DSN)
    warehouse.ensure_schema()
    while True:
        try:
            n = canonextract.ingest(warehouse, root=EXPORT_DIR)
            print(f"Ingested {n} canon governance export(s).", flush=True)
        except Exception:
            print("canon ingest failed:", flush=True)
            traceback.print_exc()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
