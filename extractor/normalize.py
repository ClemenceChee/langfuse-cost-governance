"""Normalize a Langfuse observation (REST or ClickHouse shape) into one flat
fact row. This is the single place where usage/cost details are flattened, so
the cross-harness normalization belongs here too (add a per-provider mapper as
adoption grows).
"""
import json
from datetime import datetime


def _parse_iso(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _as_int(value):
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_float(value):
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _unwrap_json(value):
    """REST returns dicts; ClickHouse stores usage/cost details as JSON strings."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return None
    return None


def normalize_observation(obs: dict, project_id: str, project_name: str | None) -> dict:
    usage = _unwrap_json(obs.get("usageDetails")) or {}
    cost = _unwrap_json(obs.get("costDetails")) or {}

    input_tokens = _as_int(usage.get("input"))
    output_tokens = _as_int(usage.get("output"))
    total_tokens = _as_int(usage.get("total")) or (input_tokens + output_tokens)
    # Prompt-cache tokens come back under different key names depending on the
    # provider/harness. Sum every cache read+write key we know about (both
    # camelCase and snake_case) so the cache-hit KPI isn't silently 0.
    cache_keys = (
        "cachedInput", "cacheReadInput", "cacheCreationInput",
        "inputCacheReadTokens", "inputCacheWriteTokens",
        "cacheReadInputTokens", "cacheCreationInputTokens",
        "cache_read_input_tokens", "cache_creation_input_tokens",
    )
    cached_tokens = sum(_as_int(usage.get(k)) for k in cache_keys)
    reasoning_tokens = _as_int(usage.get("reasoning") or usage.get("reasoningTokens"))

    input_cost = _as_float(cost.get("input"))
    output_cost = _as_float(cost.get("output"))
    total_cost = _as_float(obs.get("totalCost"))
    if total_cost == 0 and (input_cost or output_cost):
        total_cost = input_cost + output_cost

    start = _parse_iso(obs.get("startTime"))
    end = _parse_iso(obs.get("endTime"))
    latency_ms = None
    if start and end:
        latency_ms = (end - start).total_seconds() * 1000.0

    tags = obs.get("tags")
    return {
        "observation_id": obs.get("id"),
        "trace_id": obs.get("traceId"),
        "project_id": obs.get("projectId") or project_id,
        "project_name": project_name,
        "user_id": obs.get("userId"),
        "session_id": obs.get("sessionId"),
        "model": obs.get("model"),
        "type": obs.get("type"),
        "name": obs.get("name"),
        "environment": obs.get("environment"),
        "start_time": start,
        "end_time": end,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cached_input_tokens": cached_tokens,
        "reasoning_tokens": reasoning_tokens,
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": total_cost,
        "level": obs.get("level"),
        "status_message": obs.get("statusMessage"),
        "tags": json.dumps(tags, default=str) if tags is not None else None,
    }


def normalize_score(score: dict, project_id: str, project_name: str | None) -> dict:
    """Normalize a Langfuse score (eval result) into one fact_score row.

    Scores v3 nests the subject under ``subject`` (kind/id/traceId); older
    v1/v2 shapes expose a flat ``observationId``/``traceId``. Handle both.
    """
    subject = score.get("subject") or {}
    observation_id = score.get("observationId")
    if not observation_id and subject.get("kind") == "OBSERVATION":
        observation_id = subject.get("id")
    trace_id = score.get("traceId") or subject.get("traceId")
    return {
        "score_id": score.get("id"),
        "trace_id": trace_id,
        "observation_id": observation_id,
        "project_id": score.get("projectId") or project_id,
        "project_name": project_name,
        "name": score.get("name"),
        "value": _as_float(score.get("value")),
        "source": score.get("source"),
        "timestamp": _parse_iso(score.get("timestamp")),
    }
