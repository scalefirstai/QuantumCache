"""
GET /api/v1/skills/{skill_id}  →  SkillDetail

Shape matches `apps/ui/src/types/skill.ts`. Only `retrieval-hybrid` is
modelled today; others 404. Future skills add a `skill_id → builder`
entry below.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import Container, container

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


def _require_manifest(c: Container, name: str) -> dict:
    data = c.manifests.get(name)
    if data is None:
        raise HTTPException(
            status_code=503,
            detail=f"Required manifest '{name}' is missing — run the bootstrap pipeline.",
        )
    return data


@router.get("/{skill_id}")
def get_skill(skill_id: str) -> dict:
    if skill_id != "retrieval-hybrid":
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")
    c = container()
    eval_report = _require_manifest(c, "eval-v0-baseline")
    hybrid = _require_manifest(c, "hybrid-smoke")
    os_report = _require_manifest(c, "opensearch-index")
    qdrant_report = _require_manifest(c, "qdrant-index")
    return c.builders.build_skill(eval_report, hybrid, os_report, qdrant_report)
