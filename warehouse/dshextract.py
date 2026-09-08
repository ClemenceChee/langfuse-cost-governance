"""Ingest DeepSeek Harness (DSH) session logs into the analytics warehouse.

DSH records every session as a JSONL event stream (zstd) under
~/.dsh/sessions/<project>/<session>/session.jsonl.zstd. Token usage is emitted
on each streaming chunk as a *cumulative* running total, so we ingest only the
`assistant/message` events (one per completed model response) and take their
final `usage`.

`cacheReadTokens` is a session-level counter, not a per-call value, so the
per-call cache read is its delta between consecutive messages (clamped to the
call's input tokens). Cost is computed from the `model_prices` table (seeded
with DeepSeek V4 off-peak pricing).

Only metadata is kept (session, project, model, token counts, cost,
timestamp). Message content never leaves the DSH logs.
"""
import glob
import json
import os
import re
from datetime import datetime, timezone

DSH_SESSIONS_DIR = os.path.expanduser(
    os.environ.get("DSH_SESSIONS_DIR", "~/.dsh/sessions")
)

# DSH names a session directory after the absolute project path, slugified
# ("-home-alice-work-myproject"). Strip the leading home-<user>- segment so the
# project reads as "work-myproject". Override with DSH_PROJECT_PREFIX when your
# layout differs.
_HOME_PREFIX = re.compile(r"^home-[^-]+-")

# Attribution for locally harvested sessions. DSH logs carry no user identity,
# so this is a label, not an identifier: set DSH_USER_ID to attribute the spend.
DSH_USER_ID = os.environ.get("DSH_USER_ID", "local")

# DeepSeek V4 off-peak pricing, USD per 1M tokens (peak hours are 2x off-peak).
PRICES = {
    "deepseek-v4-flash": {"hit": 0.007, "miss": 0.22, "out": 0.66},
    "deepseek-v4-pro": {"hit": 0.022, "miss": 0.66, "out": 1.98},
    "deepseek-v4-flash-vision-exp": {"hit": 0.007, "miss": 0.22, "out": 0.66},
}

# Default governance targets (metric, operator, threshold, label).
TARGETS = [
    ("cache_hit_rate", "gte", 0.30, "Cache hit rate"),
    ("output_input_ratio", "gte", 0.30, "Output:input ratio"),
    ("reasoning_share", "lte", 0.25, "Reasoning token share"),
    ("cost_per_1k_tokens", "lte", 0.02, "Blended cost per 1k tokens"),
    ("burn_rate", "lte", 0.80, "Monthly budget burn"),
]


def _project(dirname: str) -> str:
    s = dirname.strip("-")
    prefix = os.environ.get("DSH_PROJECT_PREFIX")
    if prefix:
        return s[len(prefix):] if s.startswith(prefix) else s
    return _HOME_PREFIX.sub("", s, count=1)


def _ms_to_dt(ms):
    if not ms:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _read_zstd_lines(path: str):
    """Yield decoded bytes-lines from a zstd file via the `zstandard` module.

    Avoids depending on the host `zstdcat` binary so the ingest runs inside the
    api/extractor images (which ship `zstandard`) with only the file mounted.
    """
    import io
    import zstandard

    with open(path, "rb") as f:
        dctx = zstandard.ZstdDecompressor()
        with dctx.stream_reader(f) as reader:
            # stream_reader returns a raw reader (no line iteration); buffer it.
            for raw in io.BufferedReader(reader):
                yield raw


def parse_session(path: str) -> list[dict]:
    project = _project(os.path.basename(os.path.dirname(os.path.dirname(path))))
    fallback_sid = os.path.basename(os.path.dirname(path))
    session_id = None
    prev_cache = None
    rows = []
    for raw in _read_zstd_lines(path):
        line = raw.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        typ = ev.get("type")
        data = ev.get("data") or {}
        if typ == "session":
            session_id = ev.get("id")
        elif typ == "assistant/message":
            usage = data.get("usage") or {}
            it = int(usage.get("inputTokens") or 0)
            ot = int(usage.get("outputTokens") or 0)
            if not it and not ot:
                continue
            rt = int(usage.get("reasoningTokens") or 0)
            ct = int(usage.get("cacheReadTokens") or 0)

            # Per-call cache read = delta of the session-level counter, clamped.
            cached = min(it, max(0, ct - (prev_cache or 0))) if prev_cache is not None else 0
            prev_cache = ct
            miss = it - cached

            model = ((data.get("message") or {}).get("source") or {}).get("model")
            price = PRICES.get(model, {"hit": 0.0, "miss": 0.0, "out": 0.0})
            input_cost = (cached * price["hit"] + miss * price["miss"]) / 1_000_000
            output_cost = ot * price["out"] / 1_000_000
            total_cost = round(input_cost + output_cost, 6)

            ts = _ms_to_dt(ev.get("time"))
            sid = session_id or fallback_sid
            i = len(rows)
            rows.append({
                "observation_id": f"dsh-{sid}-{i}",
                "trace_id": f"dsh-{sid}-{i}",
                "project_id": project,
                "project_name": project,
                "user_id": DSH_USER_ID,
                "session_id": sid,
                "model": model or "(unknown)",
                "type": "GENERATION",
                "name": "assistant",
                "environment": "cli",
                "start_time": ts,
                "end_time": ts,
                "latency_ms": 0.0,
                "input_tokens": it,
                "output_tokens": ot,
                "total_tokens": it + ot + rt,
                "cached_input_tokens": cached,
                "reasoning_tokens": rt,
                "input_cost": round(input_cost, 6),
                "output_cost": round(output_cost, 6),
                "total_cost": total_cost,
                "level": None,
                "status_message": None,
                "tags": None,
            })
    return rows


def seed_governance(warehouse) -> None:
    """Seed the model price table and default governance targets."""
    warehouse.truncate_table("model_prices")
    warehouse.bulk_insert(
        "model_prices",
        ["model", "input_hit_per_1m", "input_miss_per_1m", "output_per_1m"],
        [(m, p["hit"], p["miss"], p["out"]) for m, p in PRICES.items()],
    )
    warehouse.truncate_table("targets")
    warehouse.bulk_insert(
        "targets",
        ["metric", "op", "threshold", "label"],
        TARGETS,
    )


def ingest(warehouse, root: str | None = None, truncate: bool = False) -> int:
    root = root or DSH_SESSIONS_DIR
    warehouse.ensure_schema()
    if truncate:
        warehouse.truncate_table("fact_observation")
    seed_governance(warehouse)
    total = 0
    pattern = os.path.join(root, "*", "*", "session.jsonl.zstd")
    for path in sorted(glob.glob(pattern)):
        rows = parse_session(path)
        if rows:
            # Idempotent upsert keyed on observation_id: re-runs don't duplicate
            # and don't wipe rows the Langfuse extractor wrote.
            warehouse.upsert_observations(rows)
            total += len(rows)
    return total
