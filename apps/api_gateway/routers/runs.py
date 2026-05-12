"""
GET /api/v1/runs              → RunIndexEntry[]
GET /api/v1/runs/{run_id}     → RunView

Shapes match `apps/ui/src/types/run.ts` and the fixtures under
`apps/ui/src/mocks/fixtures/runs*`. The transform from sealed-run JSON to
RunView is shared with `data/bootstrap/12_build_ui_fixtures.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import container

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.get("")
def list_runs() -> list[dict]:
    c = container()
    out: list[dict] = []
    for run_id in c.runs.list_run_ids():
        sealed = c.runs.get_sealed_run(run_id)
        if sealed is None:
            continue
        view = c.builders.build_run_view(sealed)
        out.append({
            "runId":           view["runId"],
            "client":          view["client"],
            "framework":       view["framework"],
            "verdict":         view["verdict"],
            "sealedAt":        view["sealedAt"],
            "questionPreview": c.builders.truncate(view.get("rawQuestion") or "", 120),
        })
    return out


@router.get("/{run_id}")
def get_run(run_id: str) -> dict:
    c = container()
    sealed = c.runs.get_sealed_run(run_id)
    if sealed is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return c.builders.build_run_view(sealed)
