"""Warehouse base class: shared orchestration + KPI methods.

Subclasses implement the backend mechanics (connect/execute/insert); the KPI
logic lives here and in `sql.py`, so it stays backend-agnostic.
"""
import calendar
import re
from datetime import date, datetime, timezone
from statistics import mean, stdev

from . import sql
from .sql import (
    DIM_POLICY_COLUMNS,
    FACT_COLUMNS,
    FACT_GOVERNANCE_COLUMNS,
    FACT_GOVERNANCE_DIVERGENCE_COLUMNS,
    FACT_SCORE_COLUMNS,
)

# Defense-in-depth for any free-text value interpolated into SQL (the HTTP layer
# also sanitizes; this protects non-HTTP callers too). Excludes quotes, semicolons
# and comment markers; allows real model names like "gpt-4.1-mini".
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9 .:_+\-]+$")


def _require_safe(value: str | None) -> str | None:
    if value is not None and not _SAFE_NAME_RE.fullmatch(value):
        raise ValueError(f"Unsafe value: {value!r}")
    return value


class Warehouse:
    dialect = None  # set by subclass

    def __init__(self, dsn: str):
        self.dsn = dsn

    # -- backend contract (implement in subclass) -----------------------------
    def query(self, sql_text: str, params=()) -> list[dict]:
        raise NotImplementedError

    def execute(self, sql_text: str, params=()) -> None:
        raise NotImplementedError

    def executemany(self, sql_text: str, rows) -> None:
        raise NotImplementedError

    def insert_native(self, table: str, columns: list[str], rows) -> None:
        """Native insert (ClickHouse client.insert)."""
        raise NotImplementedError

    def truncate_table(self, table: str) -> None:
        raise NotImplementedError

    # -- shared logic ---------------------------------------------------------

    def ensure_schema(self) -> None:
        for stmt in sql.schema_statements(self.dialect):
            self.execute(stmt)
        for stmt in sql.migration_statements(self.dialect):
            self.execute(stmt)
        # Drop marts first: CREATE OR REPLACE VIEW can't reorder/rename columns,
        # so a fresh drop lets schema evolution change a view's shape.
        for stmt in sql.drop_view_statements(self.dialect):
            self.execute(stmt)
        for stmt in sql.view_statements(self.dialect):
            self.execute(stmt)

    def upsert_observations(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        tuples = [tuple(r.get(c) for c in FACT_COLUMNS) for r in rows]
        stmt = sql.upsert_statement(self.dialect)
        if stmt:
            self.executemany(stmt, tuples)
        else:
            self.insert_native("fact_observation", FACT_COLUMNS, tuples)
        self.lazy_register_users({r["user_id"] for r in rows if r.get("user_id")})
        self.mark_synced()
        return len(rows)

    def upsert_scores(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        tuples = [tuple(r.get(c) for c in FACT_SCORE_COLUMNS) for r in rows]
        stmt = sql.upsert_score_statement(self.dialect)
        if stmt:
            self.executemany(stmt, tuples)
        else:
            self.insert_native("fact_score", FACT_SCORE_COLUMNS, tuples)
        return len(rows)

    def upsert_policies(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        tuples = [tuple(r.get(c) for c in DIM_POLICY_COLUMNS) for r in rows]
        stmt = sql.upsert_policy_statement(self.dialect)
        if stmt:
            self.executemany(stmt, tuples)
        else:
            self.insert_native("dim_policy", DIM_POLICY_COLUMNS, tuples)
        return len(rows)

    def upsert_governance(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        tuples = [tuple(r.get(c) for c in FACT_GOVERNANCE_COLUMNS) for r in rows]
        stmt = sql.upsert_governance_statement(self.dialect)
        if stmt:
            self.executemany(stmt, tuples)
        else:
            self.insert_native("fact_governance", FACT_GOVERNANCE_COLUMNS, tuples)
        return len(rows)

    def upsert_governance_divergence(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        tuples = [
            tuple(r.get(c) for c in FACT_GOVERNANCE_DIVERGENCE_COLUMNS) for r in rows
        ]
        stmt = sql.upsert_governance_divergence_statement(self.dialect)
        if stmt:
            self.executemany(stmt, tuples)
        else:
            self.insert_native(
                "fact_governance_divergence", FACT_GOVERNANCE_DIVERGENCE_COLUMNS, tuples
            )
        return len(rows)

    def lazy_register_users(self, user_ids) -> None:
        if not getattr(self.dialect, "register_users_lazily", True):
            return
        user_ids = [u for u in user_ids if u]
        if not user_ids:
            return
        stmt = sql.dim_user_ignore_statement(self.dialect)
        if stmt:
            self.executemany(stmt, [(u,) for u in user_ids])
        else:
            self.insert_native("dim_user", ["user_id"], [(u,) for u in user_ids])

    def mark_synced(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        stmt = sql.sync_upsert_statement(self.dialect)
        if stmt:
            self.execute(stmt, [now_iso])
        else:
            self.insert_native(
                "sync_state", ["key", "value"], [("last_sync_at", now_iso)]
            )

    def bulk_insert(self, table: str, columns: list[str], rows) -> None:
        if not rows:
            return
        stmt = sql.bulk_insert_statement(self.dialect, table, columns)
        if stmt:
            self.executemany(stmt, rows)
        else:
            self.insert_native(table, columns, rows)

    # -- KPI methods (used by the FastAPI layer) ------------------------------

    def overview(self) -> dict:
        mtd = self.query(sql.kpi_overview_mtd(self.dialect))[0]
        wow = self.query(sql.kpi_overview_wow(self.dialect))[0]
        cache_hit = None
        if mtd.get("input_tokens_mtd"):
            cache_hit = round(mtd["cached_tokens_mtd"] / mtd["input_tokens_mtd"], 4)
        out_in = None
        if mtd.get("input_tokens_mtd"):
            out_in = round(mtd["output_tokens_mtd"] / mtd["input_tokens_mtd"], 4)
        wow_pct = None
        if wow.get("prev7"):
            wow_pct = round((wow["last7"] - wow["prev7"]) / wow["prev7"] * 100, 1)
        cost_per_dev = None
        if mtd.get("active_users_mtd"):
            cost_per_dev = round(mtd["cost_mtd"] / mtd["active_users_mtd"], 2)
        avg_cost_per_session = None
        if mtd.get("sessions_mtd"):
            avg_cost_per_session = round(mtd["cost_mtd"] / mtd["sessions_mtd"], 4)
        return {
            **mtd,
            "cache_hit_rate": cache_hit,
            "output_input_ratio": out_in,
            "cost_per_active_dev": cost_per_dev,
            "avg_cost_per_session": avg_cost_per_session,
            "wow_cost_pct": wow_pct,
        }

    def daily(self, col: str, days: int) -> list[dict]:
        rows = self.query(sql.kpi_daily(self.dialect, col, days))
        for r in rows:
            if isinstance(r.get("day"), (date, datetime)):
                r["day"] = r["day"].isoformat()
        return rows

    def top(self, col: str, metric_col: str, days: int, limit: int) -> list[dict]:
        return self.query(sql.kpi_top(self.dialect, col, metric_col, days, limit))

    def efficiency(self) -> list[dict]:
        return self.query(sql.kpi_efficiency(self.dialect))

    def governance(self) -> dict:
        budget = self.query(sql.kpi_governance_budget(self.dialect))
        monthly_budget = float(budget[0]["budget_usd"]) if budget else None
        mtd = self.query(sql.kpi_governance_mtd(self.dialect))[0]
        unattributed = self.query(
            sql.kpi_governance_unattributed(self.dialect)
        )[0]["cost"]

        mtd_cost = float(mtd["mtd_cost"] or 0.0)
        unattributed = float(unattributed or 0.0)
        burn_rate = round(mtd_cost / monthly_budget, 4) if monthly_budget else None
        unattributed_pct = round(unattributed / mtd_cost, 4) if mtd_cost else None

        total_30d = self.query(sql.kpi_total_days_cost(self.dialect, 30))[0]["total_cost"]
        top5 = self.query(sql.kpi_concentration(self.dialect, 30, 5))[0]["top_cost"]
        concentration_pct = round(top5 / total_30d, 4) if total_30d else None

        return {
            "mtd_cost": mtd_cost,
            "monthly_budget": monthly_budget,
            "burn_rate": burn_rate,
            "active_users": mtd["active_users"],
            "unattributed_cost": round(unattributed, 6),
            "unattributed_pct": unattributed_pct,
            "concentration_top5_pct": concentration_pct,
        }

    def behaviour(self) -> dict:
        """Behaviour governance KPIs from the canon export tables.

        Returns the latest snapshot metrics + the ratified-policy registry +
        the model x task-key divergence aggregate. Empty state returns 200 with
        null metrics and empty lists (never an error).
        """
        snapshot = self.query(sql.kpi_governance_snapshot(self.dialect))
        policy_rows = self.query(sql.kpi_governance_policies(self.dialect))
        divergence_rows = self.query(sql.kpi_governance_divergence(self.dialect))

        def _int(v):
            return int(v) if v is not None else 0

        if snapshot:
            s = snapshot[0]
            metrics = {
                "ttrp_ms": int(s["ttrp_ms"]) if s.get("ttrp_ms") is not None else None,
                "precision14": {
                    "numerator": _int(s.get("precision14_numerator")),
                    "denominator": _int(s.get("precision14_denominator")),
                    "ratio": (
                        float(s["precision14_ratio"])
                        if s.get("precision14_ratio") is not None
                        else None
                    ),
                },
                "proposals": {
                    "total": _int(s.get("proposals_total")),
                    "pending": _int(s.get("proposals_pending")),
                    "ratified": _int(s.get("proposals_ratified")),
                    "rejected": _int(s.get("proposals_rejected")),
                    "decayed": _int(s.get("proposals_decayed")),
                },
            }
        else:
            metrics = {
                "ttrp_ms": None,
                "precision14": {"numerator": 0, "denominator": 0, "ratio": None},
                "proposals": {
                    "total": 0, "pending": 0, "ratified": 0, "rejected": 0, "decayed": 0,
                },
            }

        policies = []
        for p in policy_rows:
            promoted = p.get("promoted_at")
            if isinstance(promoted, (date, datetime)):
                promoted = promoted.isoformat()
            policies.append({
                "rule_key": p["rule_key"],
                "project_id": p.get("project_id"),
                "kind": p.get("kind"),
                "status": p.get("status"),
                "confidence": (
                    float(p["confidence"]) if p.get("confidence") is not None else None
                ),
                "promoted_at": promoted,
                "operator": p.get("operator"),
                "evidence_traces": _int(p.get("evidence_traces")),
            })

        divergence = []
        for d in divergence_rows:
            divergence.append({
                "project_id": d.get("project_id"),
                "model": d.get("model"),
                "task_key": d.get("task_key"),
                "divergent_traces": _int(d.get("divergent_traces")),
                "total_traces": _int(d.get("total_traces")),
            })

        return {"metrics": metrics, "policies": policies, "divergence": divergence}

    def sessions(self, days: int = 30, limit: int = 20) -> dict:
        stats = self.query(sql.kpi_session_stats(self.dialect, days))[0]
        top = self.query(sql.kpi_sessions_top(self.dialect, days, limit))
        return {"stats": stats, "top": top}

    def org_daily(self, days: int) -> list[dict]:
        rows = self.query(sql.kpi_org_daily(self.dialect, days))
        for r in rows:
            if isinstance(r.get("day"), (date, datetime)):
                r["day"] = r["day"].isoformat()
            r["total_cost"] = float(r["total_cost"])
        return rows

    def anomalies(self, days: int = 30, threshold: float = 1.5, lookback: int = 14) -> dict:
        """Flag days that spike vs the trailing mean (pct), the z-score, or the
        day-of-week baseline."""
        anomalies = []
        latest = None
        for r in self.baseline(days + lookback):
            pct = (
                (r["cost"] - r["baseline_14d"]) / r["baseline_14d"]
                if r["baseline_14d"] else None
            )
            flag = (
                (pct is not None and pct > threshold - 1)
                or (r["z_score"] is not None and r["z_score"] > 2.5)
                or (r["dow_ratio"] is not None and r["dow_ratio"] > threshold)
            )
            latest = {
                "day": r["day"],
                "cost": r["cost"],
                "baseline": r["dow_baseline"] if r["dow_baseline"] is not None else r["baseline_14d"],
                "pct_change": round(pct, 4) if pct is not None else None,
                "z_score": r["z_score"],
                "dow_ratio": r["dow_ratio"],
            }
            if flag:
                anomalies.append(latest)
        return {
            "anomalies": anomalies,
            "latest": latest,
            "threshold": threshold,
            "lookback_days": lookback,
        }

    def quality(self, score_name: str | None = None, threshold: float = 0.5) -> dict:
        score_name = _require_safe(score_name)
        rows = self.query(sql.kpi_trace_outcomes(self.dialect, score_name))
        passing = [
            r for r in rows
            if r.get("best_score") is not None and r["best_score"] >= threshold
        ]
        scored = len(rows)
        passing_n = len(passing)
        scored_cost = sum(float(r["cost"] or 0.0) for r in rows)
        passing_cost = sum(float(r["cost"] or 0.0) for r in passing)
        return {
            "scored_traces": scored,
            "passing_traces": passing_n,
            "pass_rate": round(passing_n / scored, 4) if scored else None,
            "scored_cost": round(scored_cost, 6),
            "passing_cost": round(passing_cost, 6),
            "cost_per_success": round(passing_cost / passing_n, 6) if passing_n else None,
            "cost_per_scored_trace": round(scored_cost / scored, 6) if scored else None,
            "threshold": threshold,
            "score_name": score_name or "(all)",
        }

    def targets(self) -> list[dict]:
        """Evaluate the governance targets table against current values."""
        rows = self.query(
            "SELECT metric, op, threshold, label FROM targets ORDER BY metric"
        )
        if not rows:
            return []
        o = self.overview()
        g = self.governance()
        fact = self.dialect.table_ref("fact_observation")
        rs = self.query(
            f"SELECT SUM(reasoning_tokens) AS r, SUM(total_tokens) AS t "
            f"FROM {fact} WHERE start_time >= {self.dialect.month_start('now()')}"
        )[0]
        reasoning_share = (
            float(rs["r"]) / float(rs["t"]) if rs.get("t") else None
        )
        current = {
            "cache_hit_rate": o.get("cache_hit_rate"),
            "output_input_ratio": o.get("output_input_ratio"),
            "cost_per_1k_tokens": o.get("cost_per_1k_tokens"),
            "burn_rate": g.get("burn_rate"),
            "reasoning_share": reasoning_share,
        }
        out = []
        for r in rows:
            cur = current.get(r["metric"])
            if cur is None:
                continue
            thr = float(r["threshold"])
            op = r["op"]
            passed = (cur >= thr) if op == "gte" else (cur <= thr) if op == "lte" else None
            out.append({
                "metric": r["metric"],
                "label": r["label"],
                "current": round(cur, 4),
                "threshold": thr,
                "op": op,
                "pass": passed,
            })
        return out

    # -- time-series methods --------------------------------------------------

    @staticmethod
    def _iso(v):
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, date):
            return v.isoformat()
        return str(v)

    def model_daily(self, days: int = 30, model: str | None = None) -> list[dict]:
        model = _require_safe(model)
        rows = self.query(sql.kpi_model_daily(self.dialect, days, model))
        for r in rows:
            r["day"] = self._iso(r["day"])
        return rows

    def hourly(self, days: int = 7, project: str | None = None) -> list[dict]:
        project = _require_safe(project)
        rows = self.query(sql.kpi_hourly(self.dialect, days, project))
        for r in rows:
            r["hour"] = self._iso(r["hour"])
        return rows

    def burndown(self) -> dict:
        budget = self.query(sql.kpi_governance_budget(self.dialect))
        monthly_budget = float(budget[0]["budget_usd"]) if budget else None
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1).strftime("%Y-%m-%d")
        daily = [r for r in self.org_daily(40) if r["day"] >= month_start]

        rows = []
        cumulative = 0.0
        for r in daily:
            cumulative += r["total_cost"]
            rows.append({
                "day": r["day"],
                "cost": round(r["total_cost"], 4),
                "cumulative": round(cumulative, 4),
            })
        elapsed = len(daily)
        avg_daily = cumulative / elapsed if elapsed else 0.0
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        remaining = max(days_in_month - elapsed, 0)
        projected = cumulative + avg_daily * remaining
        return {
            "budget": monthly_budget,
            "days": rows,
            "cumulative": round(cumulative, 4),
            "avg_daily": round(avg_daily, 4),
            "days_elapsed": elapsed,
            "days_remaining": remaining,
            "projected_end": round(projected, 4),
            "over_budget": (projected > monthly_budget) if monthly_budget else None,
        }

    def baseline(self, days: int = 60) -> list[dict]:
        series = self.org_daily(days)
        out = []
        for i, r in enumerate(series):
            d = date.fromisoformat(r["day"])
            cost = r["total_cost"]
            window = series[max(0, i - 14):i]
            wc = [w["total_cost"] for w in window]
            base_mean = mean(wc) if wc else None
            z = None
            if len(wc) >= 2:
                sd = stdev(wc)
                if sd > 0 and base_mean is not None:
                    z = (cost - base_mean) / sd
            dow = d.weekday()
            dow_costs = [
                w["total_cost"] for w in series[:i]
                if date.fromisoformat(w["day"]).weekday() == dow
            ][-4:]
            dow_base = mean(dow_costs) if dow_costs else None
            out.append({
                "day": r["day"],
                "cost": round(cost, 4),
                "baseline_14d": round(base_mean, 4) if base_mean is not None else None,
                "z_score": round(z, 3) if z is not None else None,
                "dow_baseline": round(dow_base, 4) if dow_base else None,
                "dow_ratio": round(cost / dow_base, 4) if dow_base else None,
            })
        return out

    def periods(self, days: int = 90) -> dict:
        series = self.org_daily(days)
        weeks = {}
        months = {}
        for r in series:
            d = date.fromisoformat(r["day"])
            wk = d.isocalendar()[:2]
            mo = (d.year, d.month)
            weeks[wk] = weeks.get(wk, 0.0) + r["total_cost"]
            months[mo] = months.get(mo, 0.0) + r["total_cost"]
        week_keys = sorted(weeks)
        week_rows = []
        for i, wk in enumerate(week_keys):
            prev = weeks[week_keys[i - 1]] if i > 0 else None
            week_rows.append({
                "period": f"{wk[0]}-W{wk[1]:02d}",
                "total_cost": round(weeks[wk], 4),
                "wow_pct": round((weeks[wk] - prev) / prev, 4) if prev else None,
            })
        month_keys = sorted(months)
        month_rows = []
        for i, mo in enumerate(month_keys):
            prev = months[month_keys[i - 1]] if i > 0 else None
            month_rows.append({
                "period": f"{mo[0]}-{mo[1]:02d}",
                "total_cost": round(months[mo], 4),
                "mom_pct": round((months[mo] - prev) / prev, 4) if prev else None,
            })
        return {"weekly": week_rows, "monthly": month_rows}

    def trend(self, days: int = 90) -> dict:
        series = self.org_daily(days)

        def slope(window):
            n = len(window)
            if n < 2:
                return None
            xs = list(range(n))
            ys = [w["total_cost"] for w in window]
            xm = mean(xs)
            ym = mean(ys)
            num = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
            den = sum((x - xm) ** 2 for x in xs)
            return num / den if den else None

        rows = []
        prev_slope = None
        change_points = []
        for i, r in enumerate(series):
            s = slope(series[max(0, i - 6):i + 1])
            s = round(s, 4) if s is not None else None
            direction = "up" if (s and s > 0.01) else ("down" if (s and s < -0.01) else "flat")
            if prev_slope is not None and s is not None:
                if (prev_slope > 0.01 and s < -0.01) or (prev_slope < -0.01 and s > 0.01):
                    change_points.append({
                        "day": r["day"],
                        "from": "up" if prev_slope > 0 else "down",
                        "to": "up" if s > 0 else "down",
                    })
            prev_slope = s
            rows.append({"day": r["day"], "cost": round(r["total_cost"], 4), "slope": s, "direction": direction})
        return {"series": rows, "change_points": change_points}

    def cohort(self, days: int = 90) -> list[dict]:
        rows = self.query(sql.kpi_user_daily(self.dialect, days))

        def _day(x):
            if isinstance(x, datetime):
                return x.date()
            if isinstance(x, date):
                return x
            return date.fromisoformat(str(x))

        def wknum(w):
            return w[0] * 52 + w[1]

        user_first = {}
        for r in rows:
            d = _day(r["day"])
            wk = d.isocalendar()[:2]
            if r["user_id"] not in user_first or wk < user_first[r["user_id"]]:
                user_first[r["user_id"]] = wk

        cohorts = {}
        for r in rows:
            uid = r["user_id"]
            d = _day(r["day"])
            wk = d.isocalendar()[:2]
            off = wknum(wk) - wknum(user_first[uid])
            key = (user_first[uid], off)
            if key not in cohorts:
                cohorts[key] = {
                    "cohort": f"{user_first[uid][0]}-W{user_first[uid][1]:02d}",
                    "week_offset": off,
                    "cost": 0.0,
                    "users": set(),
                }
            cohorts[key]["cost"] += float(r["total_cost"])
            cohorts[key]["users"].add(uid)

        out = [
            {
                "cohort": v["cohort"],
                "week_offset": v["week_offset"],
                "cost": round(v["cost"], 4),
                "users": len(v["users"]),
            }
            for v in cohorts.values()
        ]
        out.sort(key=lambda x: (x["cohort"], x["week_offset"]))
        return out
