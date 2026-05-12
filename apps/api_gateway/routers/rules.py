"""
Rule engine endpoints — spec at docs/specs/rule-engine.md.

  GET    /api/v1/rules                          → RuleSummary[]   (filter: ?engine=&status=)
  GET    /api/v1/rules/queue                    → RuleSummary[]   (status=pending_review)
  GET    /api/v1/rules/{rule_id}                → RuleDetail
  POST   /api/v1/rules                          → RuleDetail      (status=draft)
  PUT    /api/v1/rules/{rule_id}                → RuleDetail      (only draft|pending_review editable; bumps version)
  DELETE /api/v1/rules/{rule_id}                → {deleted:true}  (force=true for bootstrap)
  POST   /api/v1/rules/{rule_id}/submit         → RuleDetail      (draft → pending_review)
  POST   /api/v1/rules/{rule_id}/approve        → RuleDetail      (pending_review → active; archives prior active siblings)
  POST   /api/v1/rules/{rule_id}/reject         → RuleDetail      (pending_review → draft)
  POST   /api/v1/rules/{rule_id}/evaluate       → {fired:bool, verdict:dict}  (dry-run vs sample context)
  POST   /api/v1/rules/validate                 → {ok:bool, errors:[...]}     (DSL syntax check)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.domain.rules import (
    Rule, RuleStatus,
    apply_rules, bump_version, validate_condition, validate_rule,
)

from ..deps import container

router = APIRouter(prefix="/api/v1/rules", tags=["rules"])


# ════════════════════════════════════════════════════════════════════
# Wire-shape helpers (snake_case → camelCase)
# ════════════════════════════════════════════════════════════════════

def _to_summary(r: Rule) -> dict:
    return {
        "ruleId": r.rule_id,
        "engine": r.engine,
        "title": r.title,
        "priority": r.priority,
        "status": r.status,
        "version": r.version,
        "reviewQueue": r.review_queue,
        "tags": list(r.tags),
        "updatedAt": r.updated_at,
    }


def _to_detail(r: Rule) -> dict:
    return {
        "ruleId": r.rule_id,
        "engine": r.engine,
        "title": r.title,
        "description": r.description,
        "priority": r.priority,
        "status": r.status,
        "version": r.version,
        "when": r.when,
        "then": r.then,
        "reviewQueue": r.review_queue,
        "tags": list(r.tags),
        "createdAt": r.created_at,
        "updatedAt": r.updated_at,
        "approvedAt": r.approved_at,
        "approvedBy": r.approved_by,
        "submittedBy": r.submitted_by,
        "rationale": r.rationale,
    }


def _rule_review_queue(engine: str) -> str:
    """Which SME queue receives rule-change reviews.

    freshness rules → ops (cosmetic to date-handling)
    approval rules  → regulatory (governance / compliance impact)
    """
    return {"freshness": "ops", "approval": "regulatory"}.get(engine, "ops")


# ════════════════════════════════════════════════════════════════════
# Pydantic request bodies
# ════════════════════════════════════════════════════════════════════

class RuleCreateBody(BaseModel):
    ruleId: str = Field(min_length=3, max_length=200, pattern=r"^[A-Za-z0-9._-]+$")
    engine: str = Field(pattern=r"^(freshness|approval)$")
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    priority: int = Field(default=100, ge=1, le=9999)
    when: dict = Field(default_factory=dict)
    then: dict = Field(default_factory=dict)
    reviewQueue: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class RuleUpdateBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=1, le=9999)
    when: Optional[dict] = None
    then: Optional[dict] = None
    reviewQueue: Optional[str] = None
    tags: Optional[list[str]] = None


class SubmitBody(BaseModel):
    submittedBy: str = Field(min_length=1, max_length=200)


class ApprovalDecisionBody(BaseModel):
    approver: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=2000)


class EvaluateBody(BaseModel):
    """Dry-run a rule against a synthetic context."""
    context: dict = Field(default_factory=dict)


class ValidateBody(BaseModel):
    when: dict = Field(default_factory=dict)


# ════════════════════════════════════════════════════════════════════
# List + summary
# ════════════════════════════════════════════════════════════════════

@router.get("")
def list_rules(
    engine: Optional[str] = Query(default=None, pattern=r"^(freshness|approval)$"),
    status: Optional[str] = Query(default=None, pattern=r"^(draft|pending_review|active|archived)$"),
) -> list[dict]:
    repo = container().rules
    out = [_to_summary(r) for r in repo.list_all(engine=engine, status=status)]  # type: ignore[arg-type]
    out.sort(key=lambda d: (d["priority"], d["ruleId"]))
    return out


@router.get("/queue")
def list_review_queue(
    queue: Optional[str] = Query(default=None),
) -> list[dict]:
    """SME-facing pending review queue. Sorted by review_queue then by
    submitted/updated time so the most-stale items surface first."""
    repo = container().rules
    items: list[dict] = []
    for r in repo.list_all(status="pending_review"):
        if queue and r.review_queue != queue:
            continue
        items.append({**_to_summary(r), "submittedBy": r.submitted_by})
    items.sort(key=lambda d: (d["reviewQueue"], d["updatedAt"]))
    return items


# ════════════════════════════════════════════════════════════════════
# Detail
# ════════════════════════════════════════════════════════════════════

@router.get("/{rule_id}")
def get_rule(rule_id: str) -> dict:
    r = container().rules.get(rule_id)
    if r is None:
        raise HTTPException(404, f"Rule not found: {rule_id}")
    return _to_detail(r)


# ════════════════════════════════════════════════════════════════════
# Create / update / delete
# ════════════════════════════════════════════════════════════════════

@router.post("")
def create_rule(body: RuleCreateBody) -> dict:
    repo = container().rules
    if repo.get(body.ruleId) is not None:
        raise HTTPException(409, f"Rule already exists: {body.ruleId}")
    review_queue = body.reviewQueue or _rule_review_queue(body.engine)
    rule = Rule(
        rule_id=body.ruleId,
        engine=body.engine,  # type: ignore[arg-type]
        title=body.title,
        description=body.description,
        priority=body.priority,
        status="draft",
        version="1.0.0",
        when=body.when,
        then=body.then,
        review_queue=review_queue,
        tags=list(body.tags),
    )
    errors = validate_rule(rule)
    if errors:
        raise HTTPException(422, {"msg": "rule failed validation", "errors": errors})
    repo.upsert(rule)
    return _to_detail(rule)


@router.put("/{rule_id}")
def update_rule(rule_id: str, body: RuleUpdateBody) -> dict:
    repo = container().rules
    rule = repo.get(rule_id)
    if rule is None:
        raise HTTPException(404, f"Rule not found: {rule_id}")
    if rule.status not in ("draft", "pending_review"):
        raise HTTPException(
            400,
            f"rule {rule_id} is {rule.status}; only draft or pending_review can be edited",
        )
    if body.title is not None:
        rule.title = body.title
    if body.description is not None:
        rule.description = body.description
    if body.priority is not None:
        rule.priority = body.priority
    if body.when is not None:
        rule.when = body.when
    if body.then is not None:
        rule.then = body.then
    if body.reviewQueue is not None:
        rule.review_queue = body.reviewQueue
    if body.tags is not None:
        rule.tags = list(body.tags)

    rule.version = bump_version(rule.version, level="minor")
    # Editing a pending rule drops it back to draft — SME must re-submit.
    if rule.status == "pending_review":
        rule.status = "draft"
        rule.submitted_by = None

    errors = validate_rule(rule)
    if errors:
        raise HTTPException(422, {"msg": "rule failed validation", "errors": errors})
    repo.upsert(rule)
    return _to_detail(rule)


@router.delete("/{rule_id}")
def delete_rule(rule_id: str, force: bool = Query(default=False)) -> dict:
    repo = container().rules
    try:
        deleted = repo.delete(rule_id, force=force)
    except PermissionError as e:
        raise HTTPException(400, str(e))
    if not deleted:
        raise HTTPException(404, f"Rule not found: {rule_id}")
    return {"deleted": True, "ruleId": rule_id}


# ════════════════════════════════════════════════════════════════════
# Lifecycle transitions
# ════════════════════════════════════════════════════════════════════

@router.post("/{rule_id}/submit")
def submit_rule(rule_id: str, body: SubmitBody) -> dict:
    repo = container().rules
    rule = repo.get(rule_id)
    if rule is None:
        raise HTTPException(404, f"Rule not found: {rule_id}")
    if rule.status != "draft":
        raise HTTPException(
            400,
            f"rule {rule_id} is {rule.status}; only draft can be submitted",
        )
    rule.status = "pending_review"
    rule.submitted_by = body.submittedBy
    rule.rationale = None  # clear any prior reject rationale
    # Pin review_queue at submission time so it can't drift mid-review.
    if not rule.review_queue:
        rule.review_queue = _rule_review_queue(rule.engine)
    repo.upsert(rule)
    return _to_detail(rule)


@router.post("/{rule_id}/approve")
def approve_rule(rule_id: str, body: ApprovalDecisionBody) -> dict:
    repo = container().rules
    rule = repo.get(rule_id)
    if rule is None:
        raise HTTPException(404, f"Rule not found: {rule_id}")
    if rule.status != "pending_review":
        raise HTTPException(
            400,
            f"rule {rule_id} is {rule.status}; only pending_review can be approved",
        )
    # Archive any other active rules with the same logical id stem
    # (everything before the last `.v\d+` if present; otherwise same rule_id).
    _archive_siblings(rule.rule_id, rule.engine, exclude=rule.rule_id)

    rule.status = "active"
    rule.approved_at = _now_iso()
    rule.approved_by = body.approver
    rule.rationale = body.rationale
    repo.upsert(rule)
    return _to_detail(rule)


@router.post("/{rule_id}/reject")
def reject_rule(rule_id: str, body: ApprovalDecisionBody) -> dict:
    repo = container().rules
    rule = repo.get(rule_id)
    if rule is None:
        raise HTTPException(404, f"Rule not found: {rule_id}")
    if rule.status != "pending_review":
        raise HTTPException(
            400,
            f"rule {rule_id} is {rule.status}; only pending_review can be rejected",
        )
    rule.status = "draft"
    rule.approved_at = None
    rule.approved_by = None
    rule.rationale = body.rationale  # SME's reject note
    repo.upsert(rule)
    return _to_detail(rule)


def _archive_siblings(rule_id: str, engine: str, *, exclude: str) -> None:
    """Archive any other `active` rule of the same engine that shares this
    rule's stem. Heuristic: same engine + same `priority` + same first two
    dotted segments → "logical sibling". This keeps the engine deterministic
    (no two active rules with overlapping intents)."""
    repo = container().rules
    if "." not in rule_id:
        return
    stem = ".".join(rule_id.split(".")[:2])
    for r in repo.list_all(engine=engine, status="active"):  # type: ignore[arg-type]
        if r.rule_id == exclude:
            continue
        if ".".join(r.rule_id.split(".")[:2]) == stem and r.rule_id != exclude:
            r.status = "archived"
            repo.upsert(r)


# ════════════════════════════════════════════════════════════════════
# DSL helpers — validate + dry-run evaluate
# ════════════════════════════════════════════════════════════════════

@router.post("/validate")
def validate_dsl(body: ValidateBody) -> dict:
    errors = validate_condition(body.when)
    return {"ok": not errors, "errors": errors}


@router.post("/{rule_id}/evaluate")
def evaluate_rule(rule_id: str, body: EvaluateBody) -> dict:
    repo = container().rules
    rule = repo.get(rule_id)
    if rule is None:
        raise HTTPException(404, f"Rule not found: {rule_id}")
    fired = apply_rules([rule], body.context, first_match_only=False)
    if not fired:
        return {"ruleId": rule_id, "fired": False, "verdict": None}
    return {"ruleId": rule_id, "fired": True, "verdict": fired[0].verdict}


def _now_iso() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat()
