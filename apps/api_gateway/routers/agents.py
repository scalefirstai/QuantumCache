"""
Agent prompt editor endpoints — spec at docs/agent-prompt-editor.md.

  GET    /api/v1/agents
  GET    /api/v1/agents/{agent_id}
  GET    /api/v1/agents/{agent_id}/versions
  GET    /api/v1/agents/{agent_id}/versions/{version}
  POST   /api/v1/agents/{agent_id}/versions
  PUT    /api/v1/agents/{agent_id}/active
  GET    /api/v1/agents/{agent_id}/audit
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.ports.prompts import VersionConflict
from infra.adapters.fs_prompts import LLM_AGENTS, RULE_AGENTS

from ..deps import container
from .templates import TEMPLATES

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


def _doc_to_dict(doc) -> dict:
    return {
        "agentId": doc.agent_id,
        "agentName": doc.agent_name,
        "version": doc.version,
        "model": doc.model,
        "temperature": doc.temperature,
        "maxTokens": doc.max_tokens,
        "description": doc.description,
        "tools": list(doc.tools),
        "system": doc.system,
        "userTemplate": doc.user_template,
        "raw": doc.raw,
        "sha256": doc.sha256,
    }


def _summary(agent_id: str) -> dict:
    c = container()
    is_llm = agent_id in LLM_AGENTS
    meta = LLM_AGENTS[agent_id] if is_llm else RULE_AGENTS[agent_id]
    active = c.prompts.active_version(agent_id) if is_llm else None
    versions = c.prompts.list_versions(agent_id) if is_llm else []
    audit = c.prompts.list_audit(agent_id) if is_llm else []
    doc = c.prompts.get_document(agent_id) if is_llm and active else None
    return {
        "id": agent_id,
        "name": meta["name"],
        "kind": "llm" if is_llm else "rule",
        "model": doc.model if doc else None,
        "temperature": doc.temperature if doc else None,
        "maxTokens": doc.max_tokens if doc else None,
        "tools": list(doc.tools) if doc else list(meta.get("default_tools") or []),
        "activeVersion": active,
        "versionCount": len(versions),
        "lastEditedAt": audit[0].ts if audit else None,
    }


@router.get("")
def list_agents() -> list[dict]:
    c = container()
    return [_summary(a) for a in c.prompts.list_agent_ids()]


@router.get("/{agent_id}")
def get_agent(agent_id: str) -> dict:
    if agent_id not in LLM_AGENTS and agent_id not in RULE_AGENTS:
        raise HTTPException(404, f"Unknown agent: {agent_id}")
    c = container()
    summary = _summary(agent_id)
    meta = (LLM_AGENTS | RULE_AGENTS)[agent_id]
    doc = c.prompts.get_document(agent_id) if summary["kind"] == "llm" else None
    return {
        **summary,
        "description": meta["description"],
        "active": _doc_to_dict(doc) if doc else None,
    }


@router.get("/{agent_id}/versions")
def list_versions(agent_id: str) -> list[dict]:
    if agent_id not in LLM_AGENTS:
        raise HTTPException(404, f"Agent has no editable prompt: {agent_id}")
    versions = container().prompts.list_versions(agent_id)
    return [
        {"version": v.version, "createdAt": v.created_at, "isActive": v.is_active,
         "sha256": v.sha256, "comment": v.comment}
        for v in versions
    ]


@router.get("/{agent_id}/versions/{version}")
def get_version(agent_id: str, version: str) -> dict:
    if agent_id not in LLM_AGENTS:
        raise HTTPException(404, f"Agent has no editable prompt: {agent_id}")
    doc = container().prompts.get_document(agent_id, version)
    if doc is None:
        raise HTTPException(404, f"Version not found: {agent_id}@{version}")
    return _doc_to_dict(doc)


class CreateVersionBody(BaseModel):
    baseVersion: str
    bump: str = Field(pattern="^(patch|minor|major)$")
    system: str
    userTemplate: str
    model: Optional[str] = None
    temperature: Optional[float] = None
    maxTokens: Optional[int] = None
    description: Optional[str] = None
    tools: Optional[list[str]] = None
    comment: Optional[str] = None
    actor: str = "unknown"
    activate: bool = False


@router.post("/{agent_id}/versions")
def create_version(agent_id: str, body: CreateVersionBody) -> dict:
    if agent_id not in LLM_AGENTS:
        raise HTTPException(404, f"Agent has no editable prompt: {agent_id}")
    try:
        doc = container().prompts.create_version(
            agent_id=agent_id,
            base_version=body.baseVersion,
            bump=body.bump,
            system=body.system,
            user_template=body.userTemplate,
            model=body.model,
            temperature=body.temperature,
            max_tokens=body.maxTokens,
            description=body.description,
            tools=body.tools,
            actor=body.actor,
            comment=body.comment,
            activate=body.activate,
        )
    except VersionConflict as e:
        raise HTTPException(
            status_code=409,
            detail={"error": "version_conflict", "currentActive": e.current_active, "expected": e.expected},
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return _doc_to_dict(doc)


class ApplyTemplateBody(BaseModel):
    templateId: str
    bump: str = Field(default="minor", pattern="^(patch|minor|major)$")
    actor: str = "unknown"
    comment: Optional[str] = None
    activate: bool = True


@router.post("/{agent_id}/apply-template")
def apply_template(agent_id: str, body: ApplyTemplateBody) -> dict:
    if agent_id not in LLM_AGENTS:
        raise HTTPException(404, f"Agent has no editable prompt: {agent_id}")
    template = TEMPLATES.get(body.templateId)
    if not template:
        raise HTTPException(404, f"Template not found: {body.templateId}")
    c = container()
    base = c.prompts.get_document(agent_id)
    if base is None:
        raise HTTPException(404, f"No active prompt for {agent_id}")
    patch = template["patch"]
    new_system = (base.system + patch.get("systemSuffix", "")).strip()
    try:
        doc = c.prompts.create_version(
            agent_id=agent_id,
            base_version=base.version,
            bump=body.bump,
            system=new_system,
            user_template=base.user_template,
            model=patch.get("model"),
            temperature=patch.get("temperature"),
            max_tokens=patch.get("maxTokens"),
            description=base.description,
            tools=list(base.tools),
            actor=body.actor,
            comment=body.comment or f"Applied template: {body.templateId}",
            activate=body.activate,
            action_label="apply-template",
        )
    except VersionConflict as e:
        raise HTTPException(409, {"error": "version_conflict",
                                  "currentActive": e.current_active, "expected": e.expected})
    return _doc_to_dict(doc)


class ActivateBody(BaseModel):
    version: str
    comment: Optional[str] = None
    actor: str = "unknown"


@router.put("/{agent_id}/active")
def set_active(agent_id: str, body: ActivateBody) -> dict:
    if agent_id not in LLM_AGENTS:
        raise HTTPException(404, f"Agent has no editable prompt: {agent_id}")
    try:
        container().prompts.set_active(agent_id, body.version, body.actor, body.comment)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return get_agent(agent_id)


@router.get("/{agent_id}/audit")
def get_audit(agent_id: str) -> list[dict]:
    if agent_id not in LLM_AGENTS:
        raise HTTPException(404, f"Agent has no editable prompt: {agent_id}")
    entries = container().prompts.list_audit(agent_id)
    return [
        {"ts": e.ts, "actor": e.actor, "action": e.action,
         "fromVersion": e.from_version, "toVersion": e.to_version, "comment": e.comment}
        for e in entries
    ]
