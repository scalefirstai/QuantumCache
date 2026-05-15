"""
Opp→Deal platform endpoints — spec at docs/specs/OPP-DEAL-SPEC.md.

Eight-stage workflow surface:

  GET    /api/v1/opp-deal/opportunities                           → Opportunity[]
  POST   /api/v1/opp-deal/opportunities                           → Opportunity  (S01 intake)
  GET    /api/v1/opp-deal/opportunities/{opp_id}                  → Opportunity
  PATCH  /api/v1/opp-deal/opportunities/{opp_id}                  → Opportunity
  DELETE /api/v1/opp-deal/opportunities/{opp_id}                  → {deleted:true}

  POST   /api/v1/opp-deal/opportunities/{opp_id}/scope            → ScopeManifest   (S02)
  POST   /api/v1/opp-deal/opportunities/{opp_id}/commitments      → CommitmentSet   (S03)
  POST   /api/v1/opp-deal/opportunities/{opp_id}/complexity       → ComplexityScorecard (S04)
  POST   /api/v1/opp-deal/opportunities/{opp_id}/cost             → CostStack       (S05a)
  POST   /api/v1/opp-deal/opportunities/{opp_id}/capacity         → CapacityImpact  (S05b)
  POST   /api/v1/opp-deal/opportunities/{opp_id}/pricing          → PricingProposal (S06)
  POST   /api/v1/opp-deal/opportunities/{opp_id}/operating-model  → OperatingModelPlan (S07)
  POST   /api/v1/opp-deal/opportunities/{opp_id}/approval         → ApprovalRequest (S08)
  POST   /api/v1/opp-deal/opportunities/{opp_id}/approval/decide  → ApprovalRequest
  POST   /api/v1/opp-deal/opportunities/{opp_id}/seal             → SealedDealBundle (S08)
  GET    /api/v1/opp-deal/opportunities/{opp_id}/replay           → ReplayReport
  GET    /api/v1/opp-deal/opportunities/{opp_id}/journal          → DealJournalEvent[]
  GET    /api/v1/opp-deal/opportunities/{opp_id}/bundle           → SealedDealBundle

  GET    /api/v1/opp-deal/upm                                     → UPM catalog
  GET    /api/v1/opp-deal/apps                                    → App registry
"""

from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.domain.opp_deal import (
    ClientResolution,
    Commitment,
    EntityTreeRole,
    IntakeSource,
    Opportunity,
    RelationshipContext,
    ScopeSummary,
    now_iso,
)
from infra.adapters.fs_opp_deal import FsOppDeal

from ..deps import container

router = APIRouter(prefix="/api/v1/opp-deal", tags=["opp-deal"])


@lru_cache(maxsize=1)
def _adapter() -> FsOppDeal:
    return FsOppDeal(container().settings.manifests_dir)


# ════════════════════════════════════════════════════════════════════
# Pydantic request bodies
# ════════════════════════════════════════════════════════════════════

class EntityTreeRoleBody(BaseModel):
    role: str
    ucm_id: str
    label: str = ""


class ClientResolutionBody(BaseModel):
    ucm_id: Optional[str]
    ucm_snapshot_version: str = "ucm_v2026.05.13"
    legal_name: str
    domicile: str = ""
    client_segment: str = "asset_manager"
    entity_tree_roles: list[EntityTreeRoleBody] = Field(default_factory=list)
    kyc_status: str = "complete"
    confidence: float = 1.0


class ScopeSummaryBody(BaseModel):
    products_requested: list[str] = Field(default_factory=list)
    jurisdictions: list[str] = Field(default_factory=list)
    estimated_aum_usd: int = 0
    indicative_go_live: Optional[str] = None
    nav_strikes_per_day: int = 0
    transactions_per_year: int = 0
    capital_events_per_year: int = 0
    shareholders: int = 0


class IntakeSourceBody(BaseModel):
    channel: str
    consultant: Optional[str] = None
    received_at: Optional[str] = None
    raw_artifacts: list[str] = Field(default_factory=list)


class RelationshipBody(BaseModel):
    existing_revenue_usd_annual: int = 0
    existing_products: list[str] = Field(default_factory=list)
    cross_sell_pipeline: list[str] = Field(default_factory=list)
    at_risk_competitor_clients: list[str] = Field(default_factory=list)
    rm_user_id: Optional[str] = None
    exec_sponsor_user_id: Optional[str] = None


class OpportunityCreate(BaseModel):
    opportunity_id: Optional[str] = None
    ecrm_id: str = ""
    name: str
    source: IntakeSourceBody
    client: ClientResolutionBody
    relationship: RelationshipBody = RelationshipBody()
    scope_summary: ScopeSummaryBody


class OpportunityPatch(BaseModel):
    name: Optional[str] = None
    scope_summary: Optional[ScopeSummaryBody] = None
    relationship: Optional[RelationshipBody] = None


class CommitmentBody(BaseModel):
    commitment_id: Optional[str] = None
    canonical_id: str
    commitment_text: str
    commitment_class: str
    material: bool = True
    contract_schedule_target: str
    library_entry_hash: str = "sha256:placeholder"


class CommitmentSetBody(BaseModel):
    ddq_run_id: str
    commitments: list[CommitmentBody]


class ApprovalDecisionBody(BaseModel):
    role: str
    user_id: str
    comment: str = ""


class DispositionBody(BaseModel):
    state: str           # "lost" | "withdrawn"
    reason: str


class SourceDeclineBody(BaseModel):
    reason: str


# ════════════════════════════════════════════════════════════════════
# UPM + apps (read-only catalogs)
# ════════════════════════════════════════════════════════════════════

@router.get("/upm")
def upm_list() -> list[dict]:
    return _adapter().upm_all()


@router.get("/apps")
def app_list() -> list[dict]:
    return _adapter().app_registry_all()


# ════════════════════════════════════════════════════════════════════
# Opportunities (S01)
# ════════════════════════════════════════════════════════════════════

def _opp_to_dict(o: Opportunity) -> dict:
    d = asdict(o)
    return d


@router.get("/opportunities")
def list_opportunities() -> list[dict]:
    items = [_opp_to_dict(o) for o in _adapter().opp_list()]
    items.sort(key=lambda d: d["updated_at"], reverse=True)
    return items


@router.post("/opportunities", status_code=201)
def create_opportunity(body: OpportunityCreate) -> dict:
    a = _adapter()
    import uuid as _uuid
    opp_id = body.opportunity_id or f"opp_{_uuid.uuid4().hex[:12]}"
    if a.opp_get(opp_id):
        raise HTTPException(409, f"Opportunity already exists: {opp_id}")
    opp = Opportunity(
        opportunity_id=opp_id,
        ecrm_id=body.ecrm_id or f"006-{opp_id[-8:]}",
        status="intake",
        name=body.name,
        source=IntakeSource(
            channel=body.source.channel,
            consultant=body.source.consultant,
            received_at=body.source.received_at or now_iso(),
            raw_artifacts=list(body.source.raw_artifacts),
        ),
        client=ClientResolution(
            ucm_id=body.client.ucm_id,
            ucm_snapshot_version=body.client.ucm_snapshot_version,
            legal_name=body.client.legal_name,
            domicile=body.client.domicile,
            client_segment=body.client.client_segment,
            entity_tree_roles=[EntityTreeRole(**r.model_dump()) for r in body.client.entity_tree_roles],
            kyc_status=body.client.kyc_status,
            confidence=body.client.confidence,
        ),
        relationship=RelationshipContext(**body.relationship.model_dump()),
        scope_summary=ScopeSummary(**body.scope_summary.model_dump()),
    )
    a.opp_upsert(opp)
    a.journal_append(opp.opportunity_id, "intake",
                     {"channel": body.source.channel, "received_at": opp.source.received_at})
    if opp.client.ucm_id:
        a.journal_append(opp.opportunity_id, "resolve",
                         {"ucm_id": opp.client.ucm_id, "confidence": opp.client.confidence})
    return _opp_to_dict(opp)


@router.get("/opportunities/{opp_id}")
def get_opportunity(opp_id: str) -> dict:
    opp = _adapter().opp_get(opp_id)
    if opp is None:
        raise HTTPException(404, f"Opportunity not found: {opp_id}")
    return _opp_to_dict(opp)


@router.patch("/opportunities/{opp_id}")
def patch_opportunity(opp_id: str, body: OpportunityPatch) -> dict:
    a = _adapter()
    opp = a.opp_get(opp_id)
    if opp is None:
        raise HTTPException(404, f"Opportunity not found: {opp_id}")
    if body.name is not None:
        opp.name = body.name
    if body.scope_summary is not None:
        opp.scope_summary = ScopeSummary(**body.scope_summary.model_dump())
    if body.relationship is not None:
        opp.relationship = RelationshipContext(**body.relationship.model_dump())
    a.opp_upsert(opp)
    return _opp_to_dict(opp)


@router.delete("/opportunities/{opp_id}")
def delete_opportunity(opp_id: str) -> dict:
    if not _adapter().opp_delete(opp_id):
        raise HTTPException(404, f"Opportunity not found: {opp_id}")
    return {"deleted": True, "opportunity_id": opp_id}


# ════════════════════════════════════════════════════════════════════
# Stage triggers
# ════════════════════════════════════════════════════════════════════

@router.post("/opportunities/{opp_id}/scope")
def run_scope(opp_id: str) -> dict:
    try:
        return asdict(_adapter().scope_compute(opp_id))
    except KeyError:
        raise HTTPException(404, f"Opportunity not found: {opp_id}")


@router.get("/opportunities/{opp_id}/scope")
def get_scope(opp_id: str) -> dict:
    m = _adapter().scope_for(opp_id)
    if m is None:
        raise HTTPException(404, "scope not computed yet")
    return asdict(m)


@router.post("/opportunities/{opp_id}/commitments")
def set_commitments(opp_id: str, body: CommitmentSetBody) -> dict:
    a = _adapter()
    if a.opp_get(opp_id) is None:
        raise HTTPException(404, f"Opportunity not found: {opp_id}")
    import uuid as _uuid
    commits = [
        Commitment(
            commitment_id=c.commitment_id or f"cmt_{_uuid.uuid4().hex[:12]}",
            opportunity_id=opp_id,
            ddq_run_id=body.ddq_run_id,
            canonical_id=c.canonical_id,
            library_entry_hash=c.library_entry_hash,
            commitment_text=c.commitment_text,
            commitment_class=c.commitment_class,   # type: ignore[arg-type]
            material=c.material,
            contract_schedule_target=c.contract_schedule_target,
        )
        for c in body.commitments
    ]
    cs = a.commitments_set(opp_id, commits)
    return asdict(cs)


@router.get("/opportunities/{opp_id}/commitments")
def get_commitments(opp_id: str) -> dict:
    cs = _adapter().commitments_for(opp_id)
    if cs is None:
        return {"opportunity_id": opp_id, "ddq_run_id": None, "commitments": []}
    return asdict(cs)


@router.post("/opportunities/{opp_id}/complexity")
def run_complexity(opp_id: str) -> dict:
    try:
        return asdict(_adapter().complexity_score(opp_id))
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))


@router.get("/opportunities/{opp_id}/complexity")
def get_complexity(opp_id: str) -> dict:
    c = _adapter().complexity_for(opp_id)
    if c is None:
        raise HTTPException(404, "complexity not scored yet")
    return asdict(c)


@router.post("/opportunities/{opp_id}/cost")
def run_cost(opp_id: str) -> dict:
    try:
        return asdict(_adapter().cost_compute(opp_id))
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))


@router.get("/opportunities/{opp_id}/cost")
def get_cost(opp_id: str) -> dict:
    c = _adapter().cost_for(opp_id)
    if c is None:
        raise HTTPException(404, "cost not computed yet")
    return asdict(c)


@router.post("/opportunities/{opp_id}/capacity")
def run_capacity(opp_id: str) -> dict:
    try:
        return asdict(_adapter().capacity_compute(opp_id))
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))


@router.get("/opportunities/{opp_id}/capacity")
def get_capacity(opp_id: str) -> dict:
    c = _adapter().capacity_for(opp_id)
    if c is None:
        raise HTTPException(404, "capacity not analyzed yet")
    return asdict(c)


@router.post("/opportunities/{opp_id}/pricing")
def run_pricing(opp_id: str) -> dict:
    try:
        return asdict(_adapter().pricing_propose(opp_id))
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))


@router.get("/opportunities/{opp_id}/pricing")
def get_pricing(opp_id: str) -> dict:
    p = _adapter().pricing_for(opp_id)
    if p is None:
        raise HTTPException(404, "pricing not proposed yet")
    return asdict(p)


@router.post("/opportunities/{opp_id}/operating-model")
def run_operating_model(opp_id: str) -> dict:
    try:
        return asdict(_adapter().operating_model_design(opp_id))
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))


@router.get("/opportunities/{opp_id}/operating-model")
def get_operating_model(opp_id: str) -> dict:
    p = _adapter().operating_model_for(opp_id)
    if p is None:
        raise HTTPException(404, "operating model not designed yet")
    return asdict(p)


@router.post("/opportunities/{opp_id}/approval")
def request_approval(opp_id: str) -> dict:
    try:
        return asdict(_adapter().approval_request(opp_id))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/opportunities/{opp_id}/approval")
def get_approval(opp_id: str) -> dict:
    r = _adapter().approval_for(opp_id)
    if r is None:
        raise HTTPException(404, "no approval request")
    return asdict(r)


@router.post("/opportunities/{opp_id}/approval/decide")
def decide_approval(opp_id: str, body: ApprovalDecisionBody) -> dict:
    try:
        return asdict(_adapter().approval_decide(opp_id, body.role, body.user_id, body.comment))
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post("/opportunities/{opp_id}/seal")
def seal_deal(opp_id: str) -> dict:
    try:
        return asdict(_adapter().seal(opp_id))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/opportunities/{opp_id}/bundle")
def get_bundle(opp_id: str) -> dict:
    b = _adapter().sealed_get(opp_id)
    if b is None:
        raise HTTPException(404, "deal not sealed")
    return asdict(b)


@router.get("/opportunities/{opp_id}/replay")
def replay_deal(opp_id: str) -> dict:
    return _adapter().replay(opp_id)


@router.get("/opportunities/{opp_id}/journal")
def get_journal(opp_id: str) -> list[dict]:
    return [asdict(e) for e in _adapter().journal_for(opp_id)]


# ════════════════════════════════════════════════════════════════════
# Lifecycle helpers (advance, dispose)
# ════════════════════════════════════════════════════════════════════

@router.post("/opportunities/{opp_id}/advance")
def advance_opportunity(opp_id: str) -> dict:
    try:
        return _opp_to_dict(_adapter().advance(opp_id))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/opportunities/{opp_id}/dispose")
def dispose_opportunity(opp_id: str, body: DispositionBody) -> dict:
    try:
        return _opp_to_dict(_adapter().dispose(opp_id, body.state, body.reason))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


# ════════════════════════════════════════════════════════════════════
# eCRM source inbox (S01 pre-intake)
# ════════════════════════════════════════════════════════════════════

@router.get("/sources")
def list_sources(state: Optional[str] = None) -> list[dict]:
    items = [asdict(s) for s in _adapter().sources_list(state=state)]
    items.sort(key=lambda d: d["received_at"], reverse=True)
    return items


@router.get("/sources/{source_id}")
def get_source(source_id: str) -> dict:
    s = _adapter().source_get(source_id)
    if s is None:
        raise HTTPException(404, f"Source not found: {source_id}")
    return asdict(s)


@router.post("/sources/{source_id}/promote", status_code=201)
def promote_source(source_id: str) -> dict:
    try:
        return _opp_to_dict(_adapter().source_promote(source_id))
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post("/sources/{source_id}/decline")
def decline_source(source_id: str, body: SourceDeclineBody) -> dict:
    try:
        return asdict(_adapter().source_decline(source_id, body.reason))
    except KeyError as e:
        raise HTTPException(404, str(e))
