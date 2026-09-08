"""Extractor configuration (env-driven, 12-factor)."""
import json
import os

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


# Source of traces: "api" (REST, one key per project) | "clickhouse" (direct).
LANGFUSE_MODE = os.getenv("LANGFUSE_MODE", "api").lower()
LANGFUSE_BASE_URL = os.getenv("LANGFUSE_BASE_URL", "http://host.docker.internal:3000").rstrip("/")

# Analytics warehouse (any backend supported by warehouse/__init__.py).
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://analytics:analytics@localhost:5433/analytics"
)

LOOKBACK_DAYS = _int("LOOKBACK_DAYS", 30)
SYNC_INTERVAL_SECONDS = _int("SYNC_INTERVAL_SECONDS", 300)
BATCH_SIZE = min(_int("BATCH_SIZE", 1000), 1000)

# ClickHouse source mode (Langfuse's own ClickHouse, self-hosted).
LANGFUSE_CLICKHOUSE_URL = os.getenv("LANGFUSE_CLICKHOUSE_URL", "http://host.docker.internal:8123").rstrip("/")
LANGFUSE_CLICKHOUSE_USER = os.getenv("LANGFUSE_CLICKHOUSE_USER", "default")
LANGFUSE_CLICKHOUSE_PASSWORD = os.getenv("LANGFUSE_CLICKHOUSE_PASSWORD", "")


def load_projects() -> list[dict]:
    """Parse LANGFUSE_PROJECTS (JSON list) or fall back to single-key vars.

    LANGFUSE_PROJECTS example:
        [{"id":"app","name":"App Assistant","public_key":"pk-...","secret_key":"sk-..."}]
    """
    raw = os.getenv("LANGFUSE_PROJECTS", "").strip()
    if raw:
        projects = []
        for p in json.loads(raw):
            pk = p.get("public_key") or p.get("publicKey")
            sk = p.get("secret_key") or p.get("secretKey")
            pid = p.get("id") or p.get("name") or pk
            projects.append(
                {"id": pid, "name": p.get("name") or pid, "public_key": pk, "secret_key": sk}
            )
        return projects

    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sk = os.getenv("LANGFUSE_SECRET_KEY", "")
    if pk and sk:
        pid = os.getenv("LANGFUSE_PROJECT_ID", "(default)")
        return [{
            "id": pid,
            "name": os.getenv("LANGFUSE_PROJECT_NAME", pid),
            "public_key": pk,
            "secret_key": sk,
        }]
    return []


PROJECTS = load_projects()
