"""Direct ClickHouse reader for self-hosted Langfuse.

NOTE ON SCHEMA VERSIONING:
Langfuse's ClickHouse schema (table/column names) evolves between releases.
The SQL below targets the modern `observations` / `traces` tables and the
commonly-present columns. If your Langfuse version differs, adjust the SQL
constants here — or simply use LANGFUSE_MODE=api, which is version-safe.
Both modes feed the same normalize()/store() pipeline.
"""
import json

import requests


class ClickHouseReader:
    def __init__(self, url: str, user: str, password: str):
        self.url = url.rstrip("/")
        self.auth = (user, password) if user else None

    def _query(self, sql: str, params: dict[str, str]) -> list[dict]:
        resp = requests.post(
            self.url,
            params={"query": sql, "default_format": "JSONEachRow", **params},
            auth=self.auth,
            timeout=300,
        )
        resp.raise_for_status()
        rows = []
        for line in resp.text.splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    def fetch_traces(self, from_iso: str, to_iso: str) -> list[dict]:
        sql = """
        SELECT
            toString(id)                AS id,
            toString(user_id)           AS userId,
            toString(session_id)        AS sessionId,
            environment,
            tags
        FROM traces
        WHERE timestamp >= parseDateTimeBestEffort({from:String})
          AND timestamp <  parseDateTimeBestEffort({to:String})
        LIMIT {limit:UInt64}
        """
        return self._query(
            sql,
            {
                "param_from": from_iso,
                "param_to": to_iso,
                "param_limit": "1000000",
            },
        )

    def fetch_scores(self, from_iso: str, to_iso: str) -> list[dict]:
        sql = """
        SELECT
            toString(id)              AS id,
            toString(trace_id)        AS traceId,
            toString(observation_id)  AS observationId,
            toString(project_id)      AS projectId,
            name,
            value,
            source,
            timestamp
        FROM scores
        WHERE timestamp >= parseDateTimeBestEffort({from:String})
          AND timestamp <  parseDateTimeBestEffort({to:String})
        LIMIT {limit:UInt64}
        """
        return self._query(
            sql,
            {
                "param_from": from_iso,
                "param_to": to_iso,
                "param_limit": "1000000",
            },
        )

    def fetch_observations(self, from_iso: str, to_iso: str) -> list[dict]:
        # Aliased to the same camelCase shape the REST client returns, so both
        # modes flow through the identical normalize() function.
        sql = """
        SELECT
            toString(id)                                        AS id,
            toString(trace_id)                                  AS traceId,
            toString(project_id)                                AS projectId,
            type,
            name,
            COALESCE(NULLIF(toString(provided_model_name), ''),
                     toString(internal_model_id), '')           AS model,
            start_time                                          AS startTime,
            end_time                                            AS endTime,
            usage_details                                       AS usageDetails,
            cost_details                                        AS costDetails,
            total_cost                                          AS totalCost,
            level,
            status_message                                      AS statusMessage,
            environment
        FROM observations
        WHERE start_time >= parseDateTimeBestEffort({from:String})
          AND start_time <  parseDateTimeBestEffort({to:String})
        LIMIT {limit:UInt64}
        """
        return self._query(
            sql,
            {
                "param_from": from_iso,
                "param_to": to_iso,
                "param_limit": "1000000",
            },
        )
