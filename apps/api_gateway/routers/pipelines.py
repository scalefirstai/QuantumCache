"""
GET /api/v1/pipelines              → PipelineIndexEntry[]
GET /api/v1/pipelines/{ddq_id}     → Pipeline

Shapes match `apps/ui/src/types/pipeline.ts` and the fixtures under
`apps/ui/src/mocks/fixtures/pipelines*`. Reuses the per-question
projection from `data/bootstrap/13_build_pipeline_fixtures.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import container

router = APIRouter(prefix="/api/v1/pipelines", tags=["pipelines"])


def _pipeline_from_packet(packet: dict) -> dict:
    c = container()
    questions: list[dict] = []
    for q in packet.get("results") or []:
        run_id = q.get("run_id")
        if not run_id:
            continue
        sealed = c.runs.get_sealed_run(run_id)
        if sealed is None:
            continue
        questions.append(c.builders.build_question(q, sealed))
    return {
        "ddqId":           packet["ddq_id"],
        "subject":         packet.get("subject"),
        "from":            packet.get("from"),
        "to":              packet.get("to"),
        "rawEmlSha256":    packet.get("raw_eml_sha256"),
        "sealedAt":        packet.get("sealed_at"),
        "platformVersion": packet.get("platform_version"),
        "questionCount":   packet.get("question_count"),
        "questions":       questions,
    }


@router.get("")
def list_pipelines() -> list[dict]:
    c = container()
    out: list[dict] = []
    for ddq_id in c.runs.list_ddq_ids():
        packet = c.runs.get_sealed_packet(ddq_id)
        if packet is None:
            continue
        out.append({
            "ddqId":         packet["ddq_id"],
            "subject":       packet.get("subject"),
            "from":          packet.get("from"),
            "questionCount": packet.get("question_count"),
            "sealedAt":      packet.get("sealed_at"),
        })
    return out


@router.get("/{ddq_id}")
def get_pipeline(ddq_id: str) -> dict:
    c = container()
    packet = c.runs.get_sealed_packet(ddq_id)
    if packet is None:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {ddq_id}")
    return _pipeline_from_packet(packet)
