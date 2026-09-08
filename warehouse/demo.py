"""Synthetic demo data so the dashboard renders before Langfuse is wired up."""
import random
from datetime import datetime, timedelta, timezone

from .sql import FACT_COLUMNS, FACT_SCORE_COLUMNS

# (user_id, team, department); None user_id exercises the "unattributed" KPI.
DEMO_USERS = [
    ("alice", "Platform", "Engineering"),
    ("bob", "Platform", "Engineering"),
    ("carol", "Product", "Product"),
    ("erin", "Product", "Product"),
    ("dave", "Support", "Operations"),
    ("frank", "Support", "Operations"),
    (None, "Unassigned", None),
]

# (model, input $/1M tokens, output $/1M tokens, cache-hit probability)
MODELS = [
    ("claude-sonnet-4-5", 3.0, 15.0, 0.35),
    ("claude-opus-4", 15.0, 75.0, 0.10),
    ("claude-haiku-4-5", 1.0, 5.0, 0.50),
    ("gpt-4o", 2.5, 10.0, 0.0),
    ("gpt-4o-mini", 0.15, 0.60, 0.0),
]

PROJECTS = ["app-assistant", "docs-qa", "codegen"]


def _make(
    i: int, start: datetime, user: str | None, project: str, session_id: str
) -> dict:
    model, in_price, out_price, cache_p = random.choice(MODELS)

    input_tokens = random.randint(200, 8000)
    output_tokens = random.randint(50, 3000)
    cached = int(input_tokens * cache_p) if random.random() < cache_p else 0
    reasoning = (
        random.randint(0, input_tokens // 4) if model.startswith("claude") else 0
    )
    total_tokens = input_tokens + output_tokens

    in_cost = (input_tokens + cached * 0.9) / 1_000_000 * in_price
    out_cost = output_tokens / 1_000_000 * out_price
    total_cost = round(in_cost + out_cost, 6)

    latency_ms = random.randint(300, 25000)
    end = start + timedelta(milliseconds=latency_ms)

    return {
        "observation_id": f"demo-{i}",
        "trace_id": f"demo-trace-{i}",
        "project_id": project,
        "project_name": project,
        "user_id": user,
        "session_id": session_id,
        "model": model,
        "type": "GENERATION",
        "name": "chat.completion",
        "environment": "production",
        "start_time": start,
        "end_time": end,
        "latency_ms": float(latency_ms),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cached_input_tokens": cached,
        "reasoning_tokens": reasoning,
        "input_cost": round(in_cost, 6),
        "output_cost": round(out_cost, 6),
        "total_cost": total_cost,
        "level": "DEFAULT",
        "status_message": None,
        "tags": None,
    }


def generate_observations(days: int = 30, seed: int = 42) -> list[dict]:
    random.seed(seed)
    rows = []
    now = datetime.now(timezone.utc)
    i = 0
    sid = 0
    for d in range(days):
        day_start = now - timedelta(days=(days - d - 1))
        for _ in range(random.randint(15, 40)):
            user = random.choice(DEMO_USERS)[0]
            project = random.choice(PROJECTS)
            base_minute = random.randint(0, 1100)
            for t in range(random.randint(2, 10)):
                minute = base_minute + t * random.randint(2, 15)
                start = day_start.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) + timedelta(minutes=minute)
                rows.append(_make(i, start, user, project, f"demo-session-{sid}"))
                i += 1
            sid += 1
    return rows


def generate_scores(obs_rows: list[dict], seed: int = 7) -> list[dict]:
    """Attach an eval score to ~60% of traces (biased toward passing)."""
    random.seed(seed)
    trace_meta = {}
    for r in obs_rows:
        trace_meta.setdefault(
            r["trace_id"], (r["project_id"], r["project_name"], r["start_time"])
        )
    scores = []
    for i, (tid, (pid, pname, ts)) in enumerate(trace_meta.items()):
        if random.random() < 0.6:
            scores.append({
                "score_id": f"demo-score-{i}",
                "trace_id": tid,
                "observation_id": None,
                "project_id": pid,
                "project_name": pname,
                "name": "correctness",
                "value": round(random.triangular(0.2, 1.0, 0.85), 4),
                "source": "EVAL",
                "timestamp": ts,
            })
    return scores


def seed(warehouse, days: int = 30) -> int:
    warehouse.ensure_schema()
    warehouse.truncate_table("fact_observation")
    warehouse.truncate_table("fact_score")
    warehouse.truncate_table("dim_user")
    warehouse.truncate_table("budget")
    warehouse.truncate_table("targets")

    rows = generate_observations(days)
    warehouse.bulk_insert(
        "fact_observation",
        FACT_COLUMNS,
        [tuple(r.get(c) for c in FACT_COLUMNS) for r in rows],
    )

    scores = generate_scores(rows)
    warehouse.bulk_insert(
        "fact_score",
        FACT_SCORE_COLUMNS,
        [tuple(s.get(c) for c in FACT_SCORE_COLUMNS) for s in scores],
    )

    warehouse.bulk_insert(
        "dim_user",
        ["user_id", "team", "department"],
        [(u, t, d) for u, t, d in DEMO_USERS if u],
    )

    warehouse.bulk_insert(
        "budget",
        ["scope_type", "scope_id", "period", "budget_usd"],
        [
            ("global", "*", "monthly", 10000.0),
            ("team", "Platform", "monthly", 4000.0),
            ("team", "Product", "monthly", 2500.0),
        ],
    )

    warehouse.bulk_insert(
        "targets",
        ["metric", "op", "threshold", "label"],
        [
            ("cache_hit_rate", "gte", 0.30, "Cache hit rate"),
            ("output_input_ratio", "gte", 0.30, "Output:input ratio"),
            ("reasoning_share", "lte", 0.25, "Reasoning token share"),
            ("cost_per_1k_tokens", "lte", 0.02, "Blended cost per 1k tokens"),
            ("burn_rate", "lte", 0.80, "Monthly budget burn"),
        ],
    )
    return len(rows)
