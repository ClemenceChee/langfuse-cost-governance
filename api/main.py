"""FastAPI semantic layer: serves governance KPIs computed from the warehouse
views (the "calculation layer" lives in SQL, not here — this just exposes it).
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import kpis

app = FastAPI(title="AI Cost & Governance Analytics", version="0.1.0")

# The bundled topology is same-origin (nginx proxies /api/ to the API), so no
# cross-origin access is needed by default. Set CORS_ALLOW_ORIGINS to a
# comma-separated list only when the dashboard is served from another host.
CORS_ALLOW_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()
]

if CORS_ALLOW_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(kpis.router, prefix="/api/kpis")


@app.get("/api/health")
def health():
    return {"status": "ok"}
