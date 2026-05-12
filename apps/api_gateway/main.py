"""
QuantumCache API gateway — FastAPI surface for the apps/ui/ frontend.

The UI declares its endpoint contract in `apps/ui/src/api/`. This service
implements that contract by reading the same sealed runs + aggregate
manifests the orchestrator writes (data/manifests/runs/ + inbox/) and
projecting them through the existing fixture-builder functions so the
wire shape stays bit-exact with the UI fixtures.

Run locally:
    .venv/bin/uvicorn apps.api-gateway.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .deps import container
from .routers import agents, employees, models, pipelines, playground, runs, skills, templates


def create_app() -> FastAPI:
    c = container()
    app = FastAPI(
        title="QuantumCache API",
        version="0.1.0",
        description="DDQ platform read API — feeds apps/ui/.",
    )
    # Dev: accept any localhost / 127.0.0.1 port (Vite picks the next free
    # one, so pinning to :5173 is fragile). Production hosts come in via
    # DDQ_CORS_ORIGINS (exact-match allow-list).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(c.settings.cors_origins),
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict:
        runs_count = len(c.runs.list_run_ids())
        ddqs_count = len(c.runs.list_ddq_ids())
        return {
            "status": "ok",
            "runs": runs_count,
            "ddqs": ddqs_count,
            "runs_backend": c.settings.runs_backend,
            "runs_bucket": c.settings.runs_bucket if c.settings.runs_backend == "s3" else None,
            "mongo": "live" if c.mongo is not None else "off",
        }

    app.include_router(runs.router)
    app.include_router(pipelines.router)
    app.include_router(employees.router)
    app.include_router(skills.router)
    app.include_router(agents.router)
    app.include_router(models.router)
    app.include_router(templates.router)
    app.include_router(playground.router)
    return app


app = create_app()
