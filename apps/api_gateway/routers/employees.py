"""
GET /api/v1/employees/{id}                    → EmployeeConsole
GET /api/v1/employees/{id}/reviews/{period}   → PerformanceReview

Shapes match `apps/ui/src/types/employee.ts` and `…/review.ts`. Today only
`id == "aria"` is wired (single bootstrap user); other ids 404. The aggregate
manifests come from the bootstrap pipeline.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import Container, container

router = APIRouter(prefix="/api/v1/employees", tags=["employees"])


def _load_runs(c: Container) -> list[dict]:
    runs: list[dict] = []
    for run_id in c.runs.list_run_ids():
        sealed = c.runs.get_sealed_run(run_id)
        if sealed is not None:
            runs.append(sealed)
    return runs


def _require_manifest(c: Container, name: str) -> dict:
    data = c.manifests.get(name)
    if data is None:
        raise HTTPException(
            status_code=503,
            detail=f"Required manifest '{name}' is missing — run the bootstrap pipeline.",
        )
    return data


@router.get("/{employee_id}")
def get_employee(employee_id: str) -> dict:
    if employee_id != "aria":
        raise HTTPException(status_code=404, detail=f"Employee not found: {employee_id}")
    c = container()
    runs = _load_runs(c)
    wire = _require_manifest(c, "wire-up")
    tx = _require_manifest(c, "taxonomy")
    lib = _require_manifest(c, "library")
    return c.builders.build_employee(runs, wire, tx, lib)


@router.get("/{employee_id}/reviews/{period}")
def get_review(employee_id: str, period: str) -> dict:
    if employee_id != "aria" or period != "q1-2026":
        raise HTTPException(
            status_code=404,
            detail=f"Review not found: {employee_id}/{period}",
        )
    c = container()
    runs = _load_runs(c)
    wire = _require_manifest(c, "wire-up")
    eval_report = _require_manifest(c, "eval-v0-baseline")
    tx = _require_manifest(c, "taxonomy")
    lib = _require_manifest(c, "library")
    return c.builders.build_review(runs, wire, eval_report, tx, lib)
