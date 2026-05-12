"""
GET /api/v1/templates  →  Template[]

Preset config bundles users can apply to any LLM agent. Application is
done via POST /api/v1/agents/{id}/apply-template — the patch is merged
into a new version (no in-place edits).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])

TEMPLATES: dict[str, dict] = {
    "conservative-compliance": {
        "name": "Conservative compliance",
        "description": (
            "Lower temperature, tighter instruction footprint. Suitable when "
            "the agent serves a regulated tier (tier1: reg / cyber / infosec)."
        ),
        "patch": {
            "temperature": 0.0,
            "maxTokens": 1024,
            "systemSuffix": (
                "\n\nReject any draft that is not fully supported by the supplied "
                "evidence bundle. When in doubt, halt and surface to legal."
            ),
        },
    },
    "fast-cheap": {
        "name": "Fast & cheap",
        "description": (
            "Drops the agent to Haiku tier with a higher temperature ceiling. "
            "Use only for tier3 canonicals where draft quality has wide tolerance."
        ),
        "patch": {
            "model": "claude-haiku-4-5",
            "temperature": 0.4,
            "maxTokens": 768,
            "systemSuffix": "",
        },
    },
}


@router.get("")
def list_templates() -> list[dict]:
    return [
        {"id": tid, **{k: v for k, v in t.items()}}
        for tid, t in TEMPLATES.items()
    ]


def get_template(template_id: str) -> dict | None:
    return TEMPLATES.get(template_id)
