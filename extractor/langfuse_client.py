"""Minimal Langfuse public REST API client (Observations v2 + Scores v3).

Langfuse v4 is observations-first: the classic ``/api/public/traces`` endpoint
is deprecated (404 on self-hosted v4), so this client reads only the current
surfaces and rebuilds nothing — v2 observations already carry userId, sessionId,
environment and tags (the trace context v1 required a separate traces call for).

Auth is HTTP Basic: public key = username, secret key = password.
Pagination is cursor-based via the ``meta.cursor`` envelope.
"""
import base64
import time

import requests


class LangfuseApiError(RuntimeError):
    pass


# Field groups for GET /api/public/v2/observations. `usage` returns
# usageDetails/costDetails/totalCost, `basic` returns userId/sessionId/
# environment, `trace_context` returns tags. `core` is always included.
OBSERVATION_FIELDS = (
    "core,basic,time,io,metadata,model,usage,metrics,trace_context"
)


class LangfuseClient:
    def __init__(self, base_url: str, public_key: str, secret_key: str):
        self.base_url = base_url.rstrip("/")
        if not public_key or not secret_key:
            raise LangfuseApiError(
                "LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not set. "
                "Create an API key under Project -> Settings -> API Keys."
            )
        token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Basic {token}",
                "Content-Type": "application/json",
            }
        )

    def _get_cursor_paginated(self, path: str, params: dict) -> list[dict]:
        """Follow cursor-based pagination until ``meta.cursor`` is empty."""
        results: list[dict] = []
        p = dict(params)
        while True:
            resp = self.session.get(
                f"{self.base_url}{path}", params=p, timeout=120
            )
            if resp.status_code == 429:
                time.sleep(2)
                continue
            resp.raise_for_status()
            body = resp.json()
            results.extend(body.get("data", []))
            meta = body.get("meta") or {}
            cursor = meta.get("cursor")
            if not cursor:
                return results
            p = dict(params)
            p["cursor"] = cursor

    def fetch_observations(
        self, from_timestamp: str, to_timestamp: str, limit: int = 1000
    ) -> list[dict]:
        return self._get_cursor_paginated(
            "/api/public/v2/observations",
            {
                "fromStartTime": from_timestamp,
                "toStartTime": to_timestamp,
                "fields": OBSERVATION_FIELDS,
                # v2 observations cap the page size at 1000.
                "limit": min(limit, 1000),
            },
        )

    def fetch_scores(
        self, from_timestamp: str, to_timestamp: str, limit: int = 100
    ) -> list[dict]:
        return self._get_cursor_paginated(
            "/api/public/v3/scores",
            {
                "fromTimestamp": from_timestamp,
                "toTimestamp": to_timestamp,
                # v3 scores cap the page size at 100.
                "limit": min(limit, 100),
            },
        )
