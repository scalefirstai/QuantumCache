"""
Dataset management endpoints — spec at docs/specs/dataset-management.md.

  GET    /api/v1/datasets                                  → DatasetSummary[]

  GET    /api/v1/datasets/knowledge                        → KnowledgeDoc[]
  GET    /api/v1/datasets/knowledge/{doc_id}               → KnowledgeDoc
  POST   /api/v1/datasets/knowledge                        → KnowledgeDoc      (create, metadata-only)
  POST   /api/v1/datasets/knowledge/upload-url             → presigned S3 PUT
  POST   /api/v1/datasets/knowledge/confirm                → KnowledgeDoc      (after PUT)
  PUT    /api/v1/datasets/knowledge/{doc_id}               → KnowledgeDoc      (update)
  DELETE /api/v1/datasets/knowledge/{doc_id}               → {deleted:true}

  GET    /api/v1/datasets/canonical                        → CanonicalDetail[]
  GET    /api/v1/datasets/canonical/{canonical_id}         → CanonicalDetail
  POST   /api/v1/datasets/canonical                        → CanonicalDetail
  PUT    /api/v1/datasets/canonical/{canonical_id}         → CanonicalDetail
  DELETE /api/v1/datasets/canonical/{canonical_id}         → {deleted:true}

  GET    /api/v1/datasets/audit                            → AuditRunSummary[]
  GET    /api/v1/datasets/audit/{run_id}                   → AuditRunDetail
  POST   /api/v1/datasets/audit/{run_id}/verify            → AuditVerifyResult
  GET    /api/v1/datasets/audit/{run_id}/redactions        → AuditRedaction[]
  POST   /api/v1/datasets/audit/{run_id}/redactions        → AuditRedaction
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import uuid
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.domain.audit_redaction import AuditRedaction
from core.domain.knowledge import KnowledgeDocument, now_iso as knowledge_now
from core.domain.taxonomy import CanonicalQuestion, FrameworkMapping

from ..deps import container

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])


# ════════════════════════════════════════════════════════════════════
# Camelcase projection helpers
# ════════════════════════════════════════════════════════════════════

def _kn_to_dict(doc: KnowledgeDocument) -> dict:
    return {
        "docId": doc.doc_id,
        "source": doc.source,
        "entity": doc.entity,
        "kind": doc.kind,
        "effectiveDate": doc.effective_date,
        "primaryDesc": doc.primary_desc,
        "docHash": doc.doc_hash,
        "contentType": doc.content_type,
        "bytes": doc.bytes,
        "url": doc.url,
        "s3Uri": doc.s3_uri,
        "tags": list(doc.tags),
        "ingestedAt": doc.ingested_at,
        "updatedAt": doc.updated_at,
        "displayTitle": doc.display_title(),
    }


def _cn_to_dict(q: CanonicalQuestion) -> dict:
    return {
        "canonicalId": q.canonical_id,
        "label": q.label,
        "description": q.description,
        "parentId": q.parent_id,
        "tier": q.tier,
        "doNotAnswer": q.do_not_answer,
        "owners": list(q.owners),
        "tags": list(q.tags),
        "frameworkMappings": [
            {"framework": m.framework, "version": m.version, "questionRef": m.question_ref}
            for m in q.framework_mappings
        ],
        "createdAt": q.created_at,
        "updatedAt": q.updated_at,
    }


def _au_summary(sealed: dict) -> dict:
    return {
        "runId": sealed["run_id"],
        "ddqId": sealed.get("ddq_id"),
        "client": sealed.get("client", ""),
        "framework": (sealed.get("input") or {}).get("framework") or sealed.get("framework", ""),
        "verdict": sealed.get("verdict", ""),
        "sealedAt": sealed.get("sealed_at"),
        "eventCount": len(sealed.get("events", [])),
        "merkleRoot": sealed.get("merkle_root"),
    }


def _au_detail(sealed: dict, redactions: list[AuditRedaction]) -> dict:
    return {
        "runId": sealed["run_id"],
        "ddqId": sealed.get("ddq_id"),
        "sealedAt": sealed.get("sealed_at"),
        "platformVersion": sealed.get("platform_version"),
        "taxonomyVersion": sealed.get("taxonomy_version"),
        "libraryVersion": sealed.get("library_version"),
        "input": sealed.get("input"),
        "verdict": sealed.get("verdict"),
        "route": sealed.get("route"),
        "merkleRoot": sealed.get("merkle_root"),
        "events": [
            {
                "eventId": e["event_id"],
                "kind": e["kind"],
                "agent": e.get("agent"),
                "ts": e.get("ts"),
                "payloadHash": e.get("payload_hash"),
                "prevHash": e.get("prev_hash"),
                "chainHash": e.get("chain_hash"),
            }
            for e in sealed.get("events", [])
        ],
        "agents": sealed.get("agents", {}),
        "redactionCount": len(redactions),
    }


def _red_to_dict(r: AuditRedaction) -> dict:
    return {
        "redactionId": r.redaction_id,
        "runId": r.run_id,
        "eventId": r.event_id,
        "field": r.field,
        "reason": r.reason,
        "actor": r.actor,
        "ts": r.ts,
    }


# ════════════════════════════════════════════════════════════════════
# Index
# ════════════════════════════════════════════════════════════════════

@router.get("")
def list_datasets() -> list[dict]:
    c = container()
    kn_count = sum(1 for _ in c.knowledge.list_all())
    cn_count = sum(1 for _ in c.canonical.list_all())
    au_count = sum(1 for _ in c.audit_dataset.list_runs())
    return [
        {
            "id": "knowledge",
            "label": "Knowledge",
            "count": kn_count,
            "lastUpdatedAt": c.knowledge.last_updated_at(),
            "description": "Source documents the platform retrieves from (filings, framework docs).",
        },
        {
            "id": "canonical",
            "label": "Canonical",
            "count": cn_count,
            "lastUpdatedAt": c.canonical.last_updated_at(),
            "description": "Taxonomy of canonical question IDs across DDQ frameworks.",
        },
        {
            "id": "audit",
            "label": "Audit",
            "count": au_count,
            "lastUpdatedAt": c.audit_dataset.last_updated_at(),
            "description": "Sealed L01 run journals (immutable, hash-chained).",
        },
    ]


# ════════════════════════════════════════════════════════════════════
# Knowledge — full CRUD
# ════════════════════════════════════════════════════════════════════

class KnowledgeCreateBody(BaseModel):
    docId: str = Field(min_length=3, max_length=200)
    source: str
    entity: str
    primaryDesc: str
    docHash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    contentType: str
    bytes: int = Field(ge=0)
    s3Uri: str
    kind: Optional[str] = None
    effectiveDate: Optional[str] = None
    url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class KnowledgeUpdateBody(BaseModel):
    primaryDesc: Optional[str] = None
    kind: Optional[str] = None
    effectiveDate: Optional[str] = None
    tags: Optional[list[str]] = None
    url: Optional[str] = None


@router.get("/knowledge")
def list_knowledge(
    source: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
) -> list[dict]:
    c = container()
    out: list[dict] = []
    for d in c.knowledge.list_all():
        if source and d.source != source:
            continue
        if tag and tag not in d.tags:
            continue
        out.append(_kn_to_dict(d))
    out.sort(key=lambda d: d["docId"])
    return out


@router.get("/knowledge/{doc_id:path}")
def get_knowledge(doc_id: str) -> dict:
    d = container().knowledge.get(doc_id)
    if d is None:
        raise HTTPException(404, f"Knowledge document not found: {doc_id}")
    return _kn_to_dict(d)


@router.post("/knowledge")
def create_knowledge(body: KnowledgeCreateBody) -> dict:
    c = container()
    if c.knowledge.get(body.docId) is not None:
        raise HTTPException(409, f"Knowledge document already exists: {body.docId}")
    doc = KnowledgeDocument(
        doc_id=body.docId,
        source=body.source,
        entity=body.entity,
        primary_desc=body.primaryDesc,
        doc_hash=body.docHash,
        content_type=body.contentType,
        bytes=body.bytes,
        s3_uri=body.s3Uri,
        ingested_at=knowledge_now(),
        kind=body.kind,
        effective_date=body.effectiveDate,
        url=body.url,
        tags=list(body.tags),
    )
    c.knowledge.upsert(doc)
    return _kn_to_dict(doc)


# ──────────────────────────────────────────────────────────────────
# Direct-to-S3 upload flow (presign + confirm)
#
# The browser PUTs file bytes straight to LocalStack `bny-ddq-knowledge-raw`
# using a presigned URL, then calls /confirm to register the metadata row.
# /confirm re-reads the object from S3 and recomputes sha256 server-side —
# the client-supplied hash is treated as a hint, not authority.
# ──────────────────────────────────────────────────────────────────

_SAFE_KEY_CHAR = re.compile(r"[^A-Za-z0-9._-]+")
_PRESIGN_TTL_SEC = 600
_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB — far above typical DDQ-corpus PDFs


def _safe_filename(name: str) -> str:
    base = name.strip().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    cleaned = _SAFE_KEY_CHAR.sub("-", base).strip("-.") or "upload"
    return cleaned[:120]


def _build_object_key(source: str, filename: str) -> str:
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y/%m/%d")
    safe_source = _SAFE_KEY_CHAR.sub("-", source).strip("-.") or "operator"
    return f"{safe_source}/{today}/{uuid.uuid4().hex[:12]}_{_safe_filename(filename)}"


class KnowledgeUploadInitBody(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    contentType: str = Field(min_length=1, max_length=200)
    sizeBytes: int = Field(ge=0, le=_MAX_UPLOAD_BYTES)
    source: str = "operator"


class KnowledgeConfirmBody(BaseModel):
    key: str = Field(min_length=1)
    docId: str = Field(min_length=3, max_length=200)
    source: str
    entity: str
    primaryDesc: str
    contentType: str
    kind: Optional[str] = None
    effectiveDate: Optional[str] = None
    url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    # Optional client-computed hash. When set, must match the server-recomputed
    # sha256 of the uploaded bytes — otherwise the upload is rejected as
    # corrupted or tampered in transit.
    clientDocHash: Optional[str] = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")


@router.post("/knowledge/upload-url")
def create_knowledge_upload_url(body: KnowledgeUploadInitBody) -> dict:
    c = container()
    bucket = c.settings.knowledge_raw_bucket
    c.ensure_knowledge_uploads_cors()
    key = _build_object_key(body.source, body.filename)
    try:
        url = c.s3().generate_presigned_url(
            "put_object",
            Params={
                "Bucket": bucket,
                "Key": key,
                "ContentType": body.contentType,
            },
            ExpiresIn=_PRESIGN_TTL_SEC,
            HttpMethod="PUT",
        )
    except Exception as e:
        raise HTTPException(503, f"S3 presign failed: {e}")
    return {
        "uploadUrl": url,
        "method": "PUT",
        "headers": {"Content-Type": body.contentType},
        "bucket": bucket,
        "key": key,
        "s3Uri": f"s3://{bucket}/{key}",
        "expiresInSec": _PRESIGN_TTL_SEC,
    }


@router.post("/knowledge/confirm")
def confirm_knowledge_upload(body: KnowledgeConfirmBody) -> dict:
    c = container()
    bucket = c.settings.knowledge_raw_bucket
    if c.knowledge.get(body.docId) is not None:
        raise HTTPException(409, f"Knowledge document already exists: {body.docId}")

    s3 = c.s3()
    # 1. Verify the object actually landed.
    try:
        head = s3.head_object(Bucket=bucket, Key=body.key)
    except Exception:
        raise HTTPException(404, f"Uploaded object not found at s3://{bucket}/{body.key}")
    bytes_actual = int(head["ContentLength"])
    content_type_actual = head.get("ContentType") or body.contentType

    # 2. Re-read bytes and recompute sha256 — content address is authoritative.
    try:
        obj = s3.get_object(Bucket=bucket, Key=body.key)
        data = obj["Body"].read()
    except Exception as e:
        raise HTTPException(503, f"Failed to read uploaded object for hashing: {e}")
    if len(data) != bytes_actual:
        raise HTTPException(500, "S3 size disagreement between HeadObject and GetObject")
    server_hash = f"sha256:{hashlib.sha256(data).hexdigest()}"
    if body.clientDocHash and body.clientDocHash != server_hash:
        raise HTTPException(
            400,
            f"clientDocHash mismatch (got {body.clientDocHash}, server {server_hash}) — upload corrupted",
        )

    doc = KnowledgeDocument(
        doc_id=body.docId,
        source=body.source,
        entity=body.entity,
        primary_desc=body.primaryDesc,
        doc_hash=server_hash,
        content_type=content_type_actual,
        bytes=bytes_actual,
        s3_uri=f"s3://{bucket}/{body.key}",
        ingested_at=knowledge_now(),
        kind=body.kind,
        effective_date=body.effectiveDate,
        url=body.url,
        tags=list(body.tags),
    )
    c.knowledge.upsert(doc)
    return _kn_to_dict(doc)


@router.put("/knowledge/{doc_id:path}")
def update_knowledge(doc_id: str, body: KnowledgeUpdateBody) -> dict:
    c = container()
    d = c.knowledge.get(doc_id)
    if d is None:
        raise HTTPException(404, f"Knowledge document not found: {doc_id}")
    if body.primaryDesc is not None:
        d.primary_desc = body.primaryDesc
    if body.kind is not None:
        d.kind = body.kind
    if body.effectiveDate is not None:
        d.effective_date = body.effectiveDate
    if body.tags is not None:
        d.tags = list(body.tags)
    if body.url is not None:
        d.url = body.url
    c.knowledge.upsert(d)
    return _kn_to_dict(d)


@router.delete("/knowledge/{doc_id:path}")
def delete_knowledge(doc_id: str) -> dict:
    if not container().knowledge.delete(doc_id):
        raise HTTPException(404, f"Knowledge document not found: {doc_id}")
    return {"deleted": True, "docId": doc_id}


# ════════════════════════════════════════════════════════════════════
# Canonical — full CRUD
# ════════════════════════════════════════════════════════════════════

class FrameworkMappingBody(BaseModel):
    framework: str
    version: str
    questionRef: str


class CanonicalCreateBody(BaseModel):
    canonicalId: str = Field(min_length=3, max_length=200, pattern=r"^[A-Za-z0-9._-]+$")
    label: str
    description: str = ""
    parentId: Optional[str] = None
    tier: int = Field(default=2, ge=1, le=3)
    doNotAnswer: bool = False
    owners: list[str] = Field(default_factory=lambda: ["operator"])
    tags: list[str] = Field(default_factory=list)
    frameworkMappings: list[FrameworkMappingBody] = Field(default_factory=list)


class CanonicalUpdateBody(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    parentId: Optional[str] = None
    tier: Optional[int] = Field(default=None, ge=1, le=3)
    doNotAnswer: Optional[bool] = None
    owners: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    frameworkMappings: Optional[list[FrameworkMappingBody]] = None


def _mappings(items: list[FrameworkMappingBody]) -> list[FrameworkMapping]:
    return [FrameworkMapping(framework=m.framework, version=m.version, question_ref=m.questionRef)
            for m in items]


@router.get("/canonical")
def list_canonical(
    framework: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
) -> list[dict]:
    c = container()
    out: list[dict] = []
    for q in c.canonical.list_all():
        if framework and not any(m.framework == framework for m in q.framework_mappings):
            continue
        if tag and tag not in q.tags:
            continue
        out.append(_cn_to_dict(q))
    out.sort(key=lambda d: d["canonicalId"])
    return out


@router.get("/canonical/{canonical_id}")
def get_canonical(canonical_id: str) -> dict:
    q = container().canonical.get(canonical_id)
    if q is None:
        raise HTTPException(404, f"Canonical not found: {canonical_id}")
    return _cn_to_dict(q)


@router.post("/canonical")
def create_canonical(body: CanonicalCreateBody) -> dict:
    c = container()
    if c.canonical.get(body.canonicalId) is not None:
        raise HTTPException(409, f"Canonical already exists: {body.canonicalId}")
    q = CanonicalQuestion(
        canonical_id=body.canonicalId,
        label=body.label,
        description=body.description,
        parent_id=body.parentId,
        framework_mappings=_mappings(body.frameworkMappings),
        tier=body.tier,
        do_not_answer=body.doNotAnswer,
        owners=list(body.owners),
        tags=list(body.tags),
    )
    c.canonical.upsert(q)
    return _cn_to_dict(q)


@router.put("/canonical/{canonical_id}")
def update_canonical(canonical_id: str, body: CanonicalUpdateBody) -> dict:
    c = container()
    q = c.canonical.get(canonical_id)
    if q is None:
        raise HTTPException(404, f"Canonical not found: {canonical_id}")
    if body.label is not None:
        q.label = body.label
    if body.description is not None:
        q.description = body.description
    if body.parentId is not None:
        q.parent_id = body.parentId
    if body.tier is not None:
        q.tier = body.tier
    if body.doNotAnswer is not None:
        q.do_not_answer = body.doNotAnswer
    if body.owners is not None:
        q.owners = list(body.owners)
    if body.tags is not None:
        q.tags = list(body.tags)
    if body.frameworkMappings is not None:
        q.framework_mappings = _mappings(body.frameworkMappings)
    c.canonical.upsert(q)
    return _cn_to_dict(q)


@router.delete("/canonical/{canonical_id}")
def delete_canonical(canonical_id: str, force: bool = Query(default=False)) -> dict:
    c = container()
    try:
        deleted = c.canonical.delete(canonical_id, force=force)
    except PermissionError as e:
        raise HTTPException(400, str(e))
    if not deleted:
        raise HTTPException(404, f"Canonical not found: {canonical_id}")
    return {"deleted": True, "canonicalId": canonical_id}


# ════════════════════════════════════════════════════════════════════
# Audit — list / detail / verify / redact (NO edit, NO delete)
# ════════════════════════════════════════════════════════════════════

class RedactionBody(BaseModel):
    eventId: str
    field: str
    reason: str
    actor: str = "operator"


@router.get("/audit")
def list_audit(
    framework: Optional[str] = Query(default=None),
    verdict: Optional[str] = Query(default=None),
) -> list[dict]:
    c = container()
    out: list[dict] = []
    for sealed in c.audit_dataset.list_runs():
        s = _au_summary(sealed)
        if framework and s["framework"] != framework:
            continue
        if verdict and s["verdict"] != verdict:
            continue
        out.append(s)
    out.sort(key=lambda d: (d["sealedAt"] or ""), reverse=True)
    return out


@router.get("/audit/{run_id}")
def get_audit(run_id: str) -> dict:
    c = container()
    sealed = c.audit_dataset.get_run(run_id)
    if sealed is None:
        raise HTTPException(404, f"Audit run not found: {run_id}")
    redactions = c.audit_dataset.list_redactions(run_id)
    return _au_detail(sealed, redactions)


@router.post("/audit/{run_id}/verify")
def verify_audit(run_id: str) -> dict:
    c = container()
    try:
        return c.audit_dataset.verify(run_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Audit run not found: {run_id}")


@router.get("/audit/{run_id}/redactions")
def list_audit_redactions(run_id: str) -> list[dict]:
    c = container()
    if c.audit_dataset.get_run(run_id) is None:
        raise HTTPException(404, f"Audit run not found: {run_id}")
    return [_red_to_dict(r) for r in c.audit_dataset.list_redactions(run_id)]


@router.post("/audit/{run_id}/redactions")
def create_audit_redaction(run_id: str, body: RedactionBody) -> dict:
    c = container()
    redaction = AuditRedaction(
        redaction_id="",
        run_id=run_id,
        event_id=body.eventId,
        field=body.field,
        reason=body.reason,
        actor=body.actor,
        ts="",
    )
    try:
        saved = c.audit_dataset.add_redaction(redaction)
    except FileNotFoundError:
        raise HTTPException(404, f"Audit run not found: {run_id}")
    return _red_to_dict(saved)
