"""Write a sample canon export document for testing the behaviour ingest.

    python scripts/sample_canon.py [out_path]

Defaults to `canon-state/canon-state.json` (the directory the `canon-ingest`
sidecar mounts). The document matches the canon/dashboard-json v1 contract
(see docs/canon-integration.md) and exercises a non-empty metrics + policies +
divergence shape.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone


def _iso(dt: datetime) -> str:
    # canon emits millisecond-precision UTC with a trailing Z
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def sample() -> dict:
    # Use the CURRENT time so the exportedAt/promotedAt fall inside Grafana's
    # default `now-30d` window (a fixed date would be filtered out by
    # $__timeFilter as "now" drifts past it).
    now = datetime.now(timezone.utc)
    return {
        "version": 1,
        "project": {"id": "prj-refunds", "name": None},
        "exportedAt": _iso(now),
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
                "promotedAt": _iso(now - timedelta(hours=1)),
                "operator": "reviewer@acme", "evidenceTraces": 6,
            },
            {
                "ruleKey": "side-effect-retry-chargeback-task-charge-reversal",
                "kind": "side-effect-retry", "status": "ratified", "confidence": 0.5,
                "promotedAt": _iso(now - timedelta(hours=2)),
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


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "canon-state/canon-state.json"
    parent = os.path.dirname(out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(sample(), f, indent=2)
        f.write("\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
