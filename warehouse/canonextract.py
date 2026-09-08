"""Ingest canon governance exports into the analytics warehouse.

canon (`ClemenceChee/canon`) writes a versioned JSON document per project via
`canon export --format json`; this module reads those files and upserts them
into the behaviour-governance tables (`dim_policy`, `fact_governance`,
`fact_governance_divergence`). Every write is idempotent and keyed on a stable
id, so re-importing the same export never duplicates rows.

The document shape is the canon/dashboard-json v1 contract (see
docs/canon-integration-prd.md):

    {
      "version": 1,
      "project": { "id": "...", "name": null },
      "exportedAt": "2025-09-01T12:00:00.000Z",
      "metrics": {
        "ttrpMs": 7200000,
        "precision14": { "numerator": 1, "denominator": 1, "ratio": 1.0 },
        "proposals": { "total": 3, "pending": 2, "ratified": 1,
                       "rejected": 0, "decayed": 0 }
      },
      "policies": [ { "ruleKey": "...", "kind": "...", "status": "ratified",
                      "confidence": 0.5, "promotedAt": "...",
                      "operator": "...", "evidenceTraces": 7 } ],
      "divergence": [ { "model": "gpt-4o", "taskKey": "refund_task",
                        "divergentTraces": 1, "totalTraces": 8 } ]
    }

Only metadata/provenance is ingested — no input/output/metadata content.
"""
import glob
import json
import os
from datetime import datetime, timezone

CANON_EXPORT_DIR = os.path.join(os.getcwd(), "canon-state")
EXPORT_VERSION = 1


def _iso_to_dt(value) -> datetime | None:
    """Parse a canon ISO timestamp (e.g. ``...Z``) into a tz-aware datetime."""
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _num(value):
    """Return a number as-is, or None for absent/null values."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_export(document: dict):
    """Turn one canon export document into (snapshot, policies, divergence)."""
    project = document.get("project") or {}
    project_id = project.get("id") or "(unknown)"
    exported_at = _iso_to_dt(document.get("exportedAt")) or datetime.now(timezone.utc)

    metrics = document.get("metrics") or {}
    precision14 = metrics.get("precision14") or {}
    proposals = metrics.get("proposals") or {}

    snapshot = {
        "snapshot_id": f"{project_id}:{exported_at.isoformat()}",
        "project_id": project_id,
        "exported_at": exported_at,
        "ttrp_ms": _num(metrics.get("ttrpMs")),
        "precision14_numerator": _int(precision14.get("numerator")),
        "precision14_denominator": _int(precision14.get("denominator")),
        "precision14_ratio": _num(precision14.get("ratio")),
        "proposals_total": _int(proposals.get("total")),
        "proposals_pending": _int(proposals.get("pending")),
        "proposals_ratified": _int(proposals.get("ratified")),
        "proposals_rejected": _int(proposals.get("rejected")),
        "proposals_decayed": _int(proposals.get("decayed")),
    }

    policies = []
    for p in document.get("policies") or []:
        policies.append({
            "rule_key": p.get("ruleKey"),
            "project_id": project_id,
            "kind": p.get("kind"),
            "status": p.get("status") or "ratified",
            "confidence": _num(p.get("confidence")),
            "promoted_at": _iso_to_dt(p.get("promotedAt")),
            "operator": p.get("operator"),
            "evidence_traces": _int(p.get("evidenceTraces")),
        })

    divergence = []
    for d in document.get("divergence") or []:
        divergence.append({
            "project_id": project_id,
            "model": d.get("model"),
            "task_key": d.get("taskKey"),
            "divergent_traces": _int(d.get("divergentTraces")),
            "total_traces": _int(d.get("totalTraces")),
        })

    return snapshot, policies, divergence


def _read_document(path: str) -> dict | None:
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    if doc.get("version") != EXPORT_VERSION:
        print(
            f"canon ingest: skipping {path} (unsupported export version "
            f"{doc.get('version')!r})",
            flush=True,
        )
        return None
    return doc


def ingest(warehouse, root: str | None = None) -> int:
    """Read every ``*.json`` export under `root` and upsert it. Returns the
    number of snapshots ingested."""
    root = root or CANON_EXPORT_DIR
    warehouse.ensure_schema()
    total = 0
    for path in sorted(glob.glob(os.path.join(root, "*.json"))):
        doc = _read_document(path)
        if doc is None:
            continue
        snapshot, policies, divergence = parse_export(doc)
        warehouse.upsert_governance([snapshot])
        warehouse.upsert_policies(policies)
        warehouse.upsert_governance_divergence(divergence)
        total += 1
    return total
