"""Extractor entrypoint.

Loops over the sync window, pulling observations+scores for every configured
Langfuse project (or all projects via ClickHouse), normalizes them into one
fact schema, and upserts into the configured warehouse. Idempotent upserts make
it safe to crash/restart; overlapping windows simply re-upsert.
"""
import logging
import time
from datetime import datetime, timedelta, timezone

import config
from clickhouse_client import ClickHouseReader
from langfuse_client import LangfuseClient
from normalize import normalize_observation, normalize_score
from warehouse import get_warehouse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("extractor")


def build_trace_map(traces: list[dict]) -> dict[str, dict]:
    return {
        t["id"]: {
            "userId": t.get("userId"),
            "sessionId": t.get("sessionId"),
            "environment": t.get("environment"),
            "tags": t.get("tags"),
        }
        for t in traces
        if t.get("id")
    }


def enrich(obs, trace_map, project_id, project_name):
    merged = dict(obs)
    trace = trace_map.get(obs.get("traceId"), {})
    for key in ("userId", "sessionId", "environment", "tags"):
        if not merged.get(key) and trace.get(key):
            merged[key] = trace[key]
    return normalize_observation(merged, project_id, project_name)


def sync_api_mode(since, now):
    obs_rows: list[dict] = []
    score_rows: list[dict] = []
    for project in config.PROJECTS:
        client = LangfuseClient(
            config.LANGFUSE_BASE_URL,
            project["public_key"],
            project["secret_key"],
        )
        # Observations v2 already carry userId/sessionId/environment/tags
        # (trace context), so no separate traces fetch is needed (v1 did).
        observations = client.fetch_observations(
            since.isoformat(), now.isoformat(), config.BATCH_SIZE
        )
        scores = client.fetch_scores(
            since.isoformat(), now.isoformat(), config.BATCH_SIZE
        )
        obs_rows.extend(
            normalize_observation(o, project["id"], project["name"])
            for o in observations
        )
        score_rows.extend(
            normalize_score(s, project["id"], project["name"]) for s in scores
        )
        log.info(
            "project=%s: %d observations, %d scores",
            project["id"], len(observations), len(scores),
        )
    return obs_rows, score_rows


def sync_clickhouse_mode(since, now):
    reader = ClickHouseReader(
        config.LANGFUSE_CLICKHOUSE_URL,
        config.LANGFUSE_CLICKHOUSE_USER,
        config.LANGFUSE_CLICKHOUSE_PASSWORD,
    )
    traces = reader.fetch_traces(since.isoformat(), now.isoformat())
    observations = reader.fetch_observations(since.isoformat(), now.isoformat())
    scores = reader.fetch_scores(since.isoformat(), now.isoformat())
    trace_map = build_trace_map(traces)
    # project_id/project_name come from the rows in ClickHouse mode.
    obs_rows = [enrich(o, trace_map, None, None) for o in observations]
    score_rows = [normalize_score(s, None, None) for s in scores]
    return obs_rows, score_rows


def run_once(warehouse) -> None:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=config.LOOKBACK_DAYS)

    if config.LANGFUSE_MODE == "clickhouse":
        obs_rows, score_rows = sync_clickhouse_mode(since, now)
    else:
        if not config.PROJECTS:
            log.warning(
                "No projects configured (set LANGFUSE_PROJECTS or "
                "LANGFUSE_PUBLIC_KEY/SECRET_KEY); nothing to sync."
            )
            return
        obs_rows, score_rows = sync_api_mode(since, now)

    written = warehouse.upsert_observations(obs_rows)
    n_scores = warehouse.upsert_scores(score_rows)
    log.info(
        "synced %d observations, %d scores (mode=%s)",
        written, n_scores, config.LANGFUSE_MODE,
    )


def main() -> None:
    warehouse = get_warehouse(config.DATABASE_URL)
    warehouse.ensure_schema()
    while True:
        try:
            run_once(warehouse)
        except Exception:
            log.exception("sync failed; retrying after interval")
        time.sleep(config.SYNC_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
