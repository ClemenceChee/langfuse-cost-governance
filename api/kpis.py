"""Thin HTTP layer over the warehouse's KPI methods.

All calculation logic lives in warehouse/sql.py + warehouse/base.py; this
module only maps HTTP query params to whitelisted dimensions and delegates.
"""
import os
import re

from fastapi import APIRouter, HTTPException, Query

from warehouse import get_warehouse

router = APIRouter()
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://analytics:analytics@localhost:5433/analytics"
)

_warehouse = get_warehouse(DATABASE_URL)
_warehouse.ensure_schema()

# Columns exposed by the mrt_daily_usage mart.
DIMENSIONS = {
    "project": "project_name",
    "team": "team",
    "user": "user_id",
    "model": "model",
}


@router.get("/overview")
def overview():
    return _warehouse.overview()


@router.get("/daily")
def daily(dimension: str = "project", days: int = Query(30, ge=1, le=365)):
    return _warehouse.daily(DIMENSIONS.get(dimension, "project_name"), days)


@router.get("/top")
def top(
    dimension: str = "user",
    metric: str = "cost",
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=100),
):
    col = DIMENSIONS.get(dimension, "user_id")
    metric_col = "total_cost" if metric == "cost" else "total_tokens"
    return _warehouse.top(col, metric_col, days, limit)


@router.get("/efficiency")
def efficiency():
    return _warehouse.efficiency()


@router.get("/governance")
def governance():
    return _warehouse.governance()


@router.get("/behaviour")
def behaviour():
    """Behaviour governance (canon) KPIs — metrics + policies + divergence."""
    return _warehouse.behaviour()


@router.get("/targets")
def targets():
    return _warehouse.targets()


@router.get("/sessions")
def sessions(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
):
    return _warehouse.sessions(days, limit)


@router.get("/anomalies")
def anomalies(
    days: int = Query(30, ge=7, le=365),
    threshold: float = Query(1.5, ge=1.0, le=10.0),
):
    return _warehouse.anomalies(days, threshold)


@router.get("/quality")
def quality(
    score_name: str | None = Query(None),
    threshold: float = Query(0.5, ge=0.0, le=1.0),
):
    # Sanitize the free-text score_name to avoid SQL injection.
    if score_name is not None and not re.fullmatch(r"[A-Za-z0-9 .:_+\-]+", score_name):
        raise HTTPException(status_code=422, detail="Invalid score_name")
    return _warehouse.quality(score_name, threshold)


def _sanitize(s: str | None) -> str | None:
    if s is not None and not re.fullmatch(r"[A-Za-z0-9 .:_+\-]+", s):
        raise HTTPException(status_code=422, detail=f"Invalid value: {s}")
    return s


@router.get("/model-daily")
def model_daily(days: int = Query(30, ge=1, le=365), model: str | None = Query(None)):
    return _warehouse.model_daily(days, _sanitize(model))


@router.get("/hourly")
def hourly(days: int = Query(7, ge=1, le=90), project: str | None = Query(None)):
    return _warehouse.hourly(days, _sanitize(project))


@router.get("/burndown")
def burndown():
    return _warehouse.burndown()


@router.get("/baseline")
def baseline(days: int = Query(60, ge=14, le=365)):
    return _warehouse.baseline(days)


@router.get("/periods")
def periods(days: int = Query(90, ge=14, le=730)):
    return _warehouse.periods(days)


@router.get("/trend")
def trend(days: int = Query(90, ge=14, le=365)):
    return _warehouse.trend(days)


@router.get("/cohort")
def cohort(days: int = Query(90, ge=14, le=730)):
    return _warehouse.cohort(days)
