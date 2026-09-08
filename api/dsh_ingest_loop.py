"""Ingest DSH session logs into the warehouse on an interval (sidecar loop).

Run as a service (see docker-compose.grafana.yml `dsh-ingest`) or directly:

    DSH_SESSIONS_DIR=/path/to/sessions \
    DATABASE_URL=postgresql://... \
    python dsh_ingest_loop.py

The ingest is an idempotent upsert keyed on observation_id, so re-runs add new
sessions without duplicating or wiping rows the Langfuse extractor wrote.
"""
import os
import time
import traceback

from warehouse import dshextract, get_warehouse

DSN = os.getenv(
    "DATABASE_URL", "postgresql://analytics:analytics@postgres:5432/analytics"
)
INTERVAL = int(os.getenv("DSH_INGEST_INTERVAL_SECONDS", "300"))


def main() -> None:
    warehouse = get_warehouse(DSN)
    warehouse.ensure_schema()
    root = os.getenv("DSH_SESSIONS_DIR") or None
    while True:
        try:
            n = dshextract.ingest(warehouse, root=root)
            print(f"Ingested {n} observations from DSH sessions.", flush=True)
        except Exception:
            print("DSH ingest failed:", flush=True)
            traceback.print_exc()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
