"""End-to-end smoke test against the configured warehouse.

    DATABASE_URL=postgresql://... python scripts/smoke.py
    DATABASE_URL=duckdb://./ci.duckdb python scripts/smoke.py
    DATABASE_URL=clickhouse://... python scripts/smoke.py

Ensures the schema, seeds demo data, and exercises every KPI endpoint,
asserting that results are non-empty and JSON-serializable.
"""
import json
import os
import sys
import tempfile

# Make the repo root importable regardless of cwd/PYTHONPATH (so `python
# scripts/smoke.py` works from anywhere, including CI).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from warehouse import canonextract, demo, get_warehouse


# A single canon export document (canon/dashboard-json v1) used to exercise the
# behaviour-governance ingest and (slice 3) endpoint across all three backends.
SAMPLE_CANON_EXPORT = {
    "version": 1,
    "project": {"id": "prj-refunds", "name": None},
    "exportedAt": "2025-09-01T12:00:00.000Z",
    "metrics": {
        "ttrpMs": 7_200_000,
        "precision14": {"numerator": 1, "denominator": 1, "ratio": 1.0},
        "proposals": {
            "total": 3, "pending": 1, "ratified": 2, "rejected": 0, "decayed": 0,
        },
    },
    "policies": [
        {
            "ruleKey": "tool-choice-refund-task-refund-standard",
            "kind": "tool-choice", "status": "ratified", "confidence": 0.65,
            "promotedAt": "2025-09-01T12:00:00.000Z",
            "operator": "reviewer@acme", "evidenceTraces": 6,
        },
        {
            "ruleKey": "side-effect-retry-chargeback-task-charge-reversal",
            "kind": "side-effect-retry", "status": "ratified", "confidence": 0.5,
            "promotedAt": "2025-09-01T11:00:00.000Z",
            "operator": "reviewer@acme", "evidenceTraces": 7,
        },
    ],
    "divergence": [
        {"model": "gpt-4o-mini", "taskKey": "refund_task",
         "divergentTraces": 1, "totalTraces": 7},
        {"model": "gpt-4o", "taskKey": "dispute_task",
         "divergentTraces": 0, "totalTraces": 9},
    ],
}


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    wh = get_warehouse(dsn)
    wh.ensure_schema()
    n = demo.seed(wh)
    assert n > 0, "seed produced no rows"

    # Behaviour governance: start from a clean slate, ingest a canon export
    # twice, and assert the writes are idempotent (no duplicated rows).
    wh.truncate_table("fact_governance")
    wh.truncate_table("dim_policy")
    wh.truncate_table("fact_governance_divergence")

    # Empty state: no canon data must return a 200-shaped payload, not an error.
    empty = wh.behaviour()
    assert empty["metrics"]["ttrp_ms"] is None
    assert empty["metrics"]["precision14"]["ratio"] is None
    assert empty["policies"] == []
    assert empty["divergence"] == []

    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "canon-state.json"), "w") as f:
            json.dump(SAMPLE_CANON_EXPORT, f)
        assert canonextract.ingest(wh, root=tmp) == 1
        assert canonextract.ingest(wh, root=tmp) == 1  # re-import must not duplicate

    def _count(table: str) -> int:
        ref = wh.dialect.table_ref(table)
        return int(wh.query(f"SELECT COUNT(*) AS n FROM {ref}")[0]["n"])

    assert _count("fact_governance") == 1, "governance snapshot duplicated"
    assert _count("dim_policy") == 2, "policy registry duplicated"
    assert _count("fact_governance_divergence") == 2, "divergence aggregate duplicated"

    payloads = {
        "overview": wh.overview(),
        "daily": wh.daily("project_name", 30),
        "top": wh.top("user_id", "total_cost", 30, 5),
        "efficiency": wh.efficiency(),
        "governance": wh.governance(),
        "behaviour": wh.behaviour(),
        "sessions": wh.sessions(30, 5),
        "anomalies": wh.anomalies(30, 1.5),
        "quality": wh.quality(None, 0.5),
        "targets": wh.targets(),
        "burndown": wh.burndown(),
        "model_daily": wh.model_daily(30),
        "hourly": wh.hourly(7),
        "cohort": wh.cohort(90),
        "baseline": wh.baseline(60),
        "periods": wh.periods(90),
        "trend": wh.trend(90),
    }

    for name, payload in payloads.items():
        json.dumps(payload)  # must not contain non-JSON types (Decimal etc.)
        if isinstance(payload, list):
            print(f"{name}: OK ({len(payload)} rows)")
        else:
            print(f"{name}: OK -> {payload}")

    assert payloads["overview"]["cost_mtd"] > 0
    assert len(payloads["daily"]) > 0
    assert len(payloads["top"]) > 0
    assert len(payloads["efficiency"]) > 0
    assert payloads["sessions"]["stats"]["sessions"] > 0
    assert len(payloads["sessions"]["top"]) > 0
    assert payloads["overview"]["sessions_mtd"] > 0
    assert payloads["anomalies"]["latest"] is not None
    assert payloads["quality"]["scored_traces"] > 0
    assert payloads["quality"]["pass_rate"] is not None
    assert len(payloads["burndown"]["days"]) > 0
    assert len(payloads["model_daily"]) > 0
    assert len(payloads["hourly"]) > 0
    assert len(payloads["cohort"]) > 0
    assert len(payloads["baseline"]) > 0
    assert len(payloads["periods"]["weekly"]) > 0
    assert len(payloads["trend"]["series"]) > 0
    assert len(payloads["targets"]) > 0
    assert payloads["behaviour"]["metrics"]["ttrp_ms"] == 7_200_000
    assert payloads["behaviour"]["metrics"]["proposals"]["ratified"] == 2
    assert len(payloads["behaviour"]["policies"]) == 2
    assert len(payloads["behaviour"]["divergence"]) == 2
    assert payloads["behaviour"]["divergence"][0]["model"] == "gpt-4o"
    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
