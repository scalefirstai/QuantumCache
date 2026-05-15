"""
Pure-domain types for the Asset Servicing Opportunity-to-Deal platform —
docs/specs/OPP-DEAL-SPEC.md. No I/O. Bit-exact replay-friendly.

Eight stages of the deal workflow are represented as immutable artifacts
that compose into a SealedDealBundle. The deal journal is the audit spine.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional


OpportunityId = str
DealId = str
ScopeManifestId = str
ComplexityScorecardId = str
CostStackId = str
CapacityImpactId = str
PricingProposalId = str
OperatingModelId = str
CommitmentId = str
ApprovalRequestId = str


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def payload_hash(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def merkle_root(hashes: list[str]) -> str:
    if not hashes:
        return "sha256:" + hashlib.sha256(b"").hexdigest()
    layer = [h.split(":", 1)[1] if ":" in h else h for h in hashes]
    while len(layer) > 1:
        nxt: list[str] = []
        for i in range(0, len(layer), 2):
            a = layer[i]
            b = layer[i + 1] if i + 1 < len(layer) else layer[i]
            nxt.append(hashlib.sha256((a + b).encode("utf-8")).hexdigest())
        layer = nxt
    return "sha256:" + layer[0]


# ════════════════════════════════════════════════════════════════════
# S01 — Opportunity, client resolution
# ════════════════════════════════════════════════════════════════════

OpportunityStatus = Literal[
    "intake", "resolving", "scoping", "ddq", "complexity",
    "cost_capacity", "pricing", "operating_model",
    "approval", "won", "lost", "withdrawn",
]

ClientSegment = Literal[
    "asset_manager", "asset_owner_pension", "sovereign", "insurance", "alts_manager",
]


@dataclass
class EntityTreeRole:
    role: str   # manco | aifm | fund_umbrella | sub_fund | share_class | plan_sponsor | mandate
    ucm_id: str
    label: str = ""


@dataclass
class IntakeSource:
    channel: Literal["rfp_email", "rm_submitted", "consultant", "cross_segment", "retender"]
    consultant: Optional[str] = None      # "bfinance" | "mercer" | "aon" | "wtw" | "cambridge"
    received_at: str = field(default_factory=now_iso)
    raw_artifacts: list[str] = field(default_factory=list)


@dataclass
class RelationshipContext:
    existing_revenue_usd_annual: int = 0
    existing_products: list[str] = field(default_factory=list)
    cross_sell_pipeline: list[str] = field(default_factory=list)
    at_risk_competitor_clients: list[str] = field(default_factory=list)
    rm_user_id: Optional[str] = None
    exec_sponsor_user_id: Optional[str] = None


@dataclass
class ScopeSummary:
    products_requested: list[str] = field(default_factory=list)
    jurisdictions: list[str] = field(default_factory=list)
    estimated_aum_usd: int = 0
    indicative_go_live: Optional[str] = None
    nav_strikes_per_day: int = 0
    transactions_per_year: int = 0
    capital_events_per_year: int = 0
    shareholders: int = 0


@dataclass
class ClientResolution:
    ucm_id: Optional[str]
    ucm_snapshot_version: str
    legal_name: str
    domicile: str
    client_segment: ClientSegment
    entity_tree_roles: list[EntityTreeRole] = field(default_factory=list)
    kyc_status: Literal["complete", "refresh_due", "new_entity_in_progress"] = "complete"
    confidence: float = 1.0      # 0.0–1.0; below 0.7 routes to manual review


@dataclass
class Opportunity:
    opportunity_id: OpportunityId
    ecrm_id: str
    status: OpportunityStatus
    source: IntakeSource
    client: ClientResolution
    relationship: RelationshipContext
    scope_summary: ScopeSummary
    name: str = ""
    ddq_run_id: Optional[str] = None
    scope_manifest_id: Optional[ScopeManifestId] = None
    complexity_id: Optional[ComplexityScorecardId] = None
    cost_stack_id: Optional[CostStackId] = None
    capacity_id: Optional[CapacityImpactId] = None
    pricing_id: Optional[PricingProposalId] = None
    operating_model_id: Optional[OperatingModelId] = None
    deal_id: Optional[DealId] = None
    disposition_reason: Optional[str] = None     # set when lost/withdrawn
    disposition_at: Optional[str] = None
    source_id: Optional[str] = None              # eCRM source if promoted from inbox
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


# ════════════════════════════════════════════════════════════════════
# S02 — Scope manifest
# ════════════════════════════════════════════════════════════════════

ScopeIssueSeverity = Literal["info", "warn", "blocking"]


@dataclass
class DeliveryStackEntry:
    app_id: str
    role: str
    load_factor: str    # e.g. "per_nav_strike", "per_holding", "per_user"


@dataclass
class ScopeLineItem:
    upm_code: str
    label: str
    jurisdiction: str
    legal_entity: str
    delivery_stack: list[DeliveryStackEntry] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class ScopeIssue:
    severity: ScopeIssueSeverity
    code: str
    message: str
    upm_code: Optional[str] = None


@dataclass
class ScopeManifest:
    scope_manifest_id: ScopeManifestId
    opportunity_id: OpportunityId
    upm_snapshot_version: str
    line_items: list[ScopeLineItem] = field(default_factory=list)
    legal_entity_assignment: dict[str, str] = field(default_factory=dict)
    derived_app_set: list[str] = field(default_factory=list)
    derived_jurisdictions: list[str] = field(default_factory=list)
    issues: list[ScopeIssue] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)

    @property
    def blocking(self) -> bool:
        return any(i.severity == "blocking" for i in self.issues)


# ════════════════════════════════════════════════════════════════════
# S03 — DDQ bridge / commitments
# ════════════════════════════════════════════════════════════════════

CommitmentClass = Literal[
    "sla", "control", "jurisdiction_coverage", "data_residency", "reporting", "other",
]


@dataclass
class Commitment:
    commitment_id: CommitmentId
    opportunity_id: OpportunityId
    ddq_run_id: str
    canonical_id: str
    library_entry_hash: str
    commitment_text: str
    commitment_class: CommitmentClass
    material: bool
    contract_schedule_target: str
    status: Literal["proposed", "approved", "amended", "withdrawn"] = "proposed"
    extracted_at: str = field(default_factory=now_iso)


@dataclass
class CommitmentSet:
    opportunity_id: OpportunityId
    ddq_run_id: str
    commitments: list[Commitment] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════
# S04 — Complexity scorecard
# ════════════════════════════════════════════════════════════════════

ComplexityTier = Literal["T1_low", "T2_standard", "T3_high", "T4_exceptional"]

COMPLEXITY_DIMENSIONS: list[str] = [
    "fund_count_structure",
    "jurisdictional_spread",
    "asset_class_breadth",
    "nav_cadence_sla",
    "regulatory_regime_coverage",
    "bespoke_reporting",
    "client_system_integration_footprint",
    "transition_aggression",
    "servicing_model_dedicated_vs_pooled",
    "data_residency_constraints",
]


@dataclass
class ComplexityDimensionScore:
    key: str
    score: int   # 1..5
    notes: str = ""


@dataclass
class ComplexityScorecard:
    complexity_id: ComplexityScorecardId
    opportunity_id: OpportunityId
    scorecard_version: str
    dimensions: list[ComplexityDimensionScore]
    weights: dict[str, float]
    composite_score: float
    tier: ComplexityTier
    rationale_narrative: str
    scored_at: str = field(default_factory=now_iso)
    scored_by: str = "system"


# ════════════════════════════════════════════════════════════════════
# S05a — Cost stack
# ════════════════════════════════════════════════════════════════════

@dataclass
class FteLine:
    function: str
    location: str
    role: str
    count: float
    fully_loaded_rate_usd: int
    year: int


@dataclass
class SubCustodyLine:
    market: str
    annual_usd: int


@dataclass
class TechRunCostLine:
    app_id: str
    annual_usd: int
    basis: str


@dataclass
class TechExpansionLine:
    app_id: str
    expansion_cost_usd: int
    one_time: bool
    lead_time_weeks: int


@dataclass
class TransitionOneTime:
    implementation_fte_usd: int = 0
    parallel_running_usd: int = 0
    data_migration_usd: int = 0
    client_integration_build_usd: int = 0


@dataclass
class RiskComplianceLine:
    function: str
    annual_usd: int


@dataclass
class CostTotals:
    year_1_total_usd: int
    year_2_total_usd: int
    year_3_total_usd: int
    five_year_npv_usd: int


@dataclass
class CostStack:
    cost_stack_id: CostStackId
    opportunity_id: OpportunityId
    horizon_years: int
    direct_fte: list[FteLine]
    sub_custody_passthrough: list[SubCustodyLine]
    technology_run_cost: list[TechRunCostLine]
    technology_capacity_expansion: list[TechExpansionLine]
    transition_one_time: TransitionOneTime
    risk_compliance_overhead: list[RiskComplianceLine]
    allocated_overhead_pct: float
    totals: CostTotals
    computed_at: str = field(default_factory=now_iso)


# ════════════════════════════════════════════════════════════════════
# S05b — Capacity impact
# ════════════════════════════════════════════════════════════════════

CapacityVerdict = Literal["fits_in_headroom", "expansion_required", "declining_risk"]


@dataclass
class AppImpact:
    app_id: str
    label: str
    projected_delta: dict[str, float]
    post_deal_utilization_pct: dict[str, float]
    verdict: CapacityVerdict
    recommended_action: str
    expansion_cost_usd: int
    lead_time_weeks: int


@dataclass
class BlockingConstraint:
    app_id: str
    constraint: str
    severity: Literal["low", "medium", "high"]


@dataclass
class CapacityImpact:
    capacity_impact_id: CapacityImpactId
    opportunity_id: OpportunityId
    app_impacts: list[AppImpact]
    blocking_constraints: list[BlockingConstraint] = field(default_factory=list)
    computed_at: str = field(default_factory=now_iso)


# ════════════════════════════════════════════════════════════════════
# S06 — Pricing proposal
# ════════════════════════════════════════════════════════════════════

@dataclass
class AssetBandFee:
    aum_band_usd_min: int
    aum_band_usd_max: int
    bp: float


@dataclass
class AssetBasedTier:
    asset_class: str
    tiers: list[AssetBandFee]


@dataclass
class TransactionalFee:
    event: str
    fee_usd: float


@dataclass
class FixedRetainer:
    service: str
    annual_usd: int


@dataclass
class FeeStructure:
    asset_based: list[AssetBasedTier]
    transactional: list[TransactionalFee]
    fixed_retainers: list[FixedRetainer]
    passthrough_oop: list[str]
    minimum_fee_floor_usd_annual: int
    term_years: int
    term_discount_pct: float
    bundled_discount_pct: float


@dataclass
class SecLendingShare:
    client_pct: int
    bny_pct: int


@dataclass
class FxRevenueModel:
    standing_instruction_margin_bp: float
    disclosure_class: Literal["transparent", "indicative", "opaque"]


@dataclass
class TotalClientValueYear:
    year: int
    direct_fee_usd: int
    sec_lending_revenue_usd: int
    fx_revenue_usd: int
    nii_on_balances_usd: int
    adjacent_revenue_usd: int


@dataclass
class TotalClientValue:
    by_year: list[TotalClientValueYear]
    five_year_total_usd: int


@dataclass
class MarginAnalysis:
    year_1_direct_margin_pct: float
    year_1_total_margin_pct: float
    five_year_npv_usd: int
    irr_pct: float
    payback_years: float


@dataclass
class SensitivityScenario:
    scenario: str
    year_1_margin_pct_delta: float
    five_year_npv_usd: int


ApprovalTier = Literal[
    "tier_1_rm_segment_head",
    "tier_2_segment_head_cfo_delegate",
    "tier_3_cfo_coo_risk",
    "tier_4_segment_ceo_cfo",
]


@dataclass
class PricingProposal:
    pricing_proposal_id: PricingProposalId
    opportunity_id: OpportunityId
    fee_structure: FeeStructure
    sec_lending: SecLendingShare
    fx_revenue: FxRevenueModel
    total_client_value: TotalClientValue
    margin_analysis: MarginAnalysis
    sensitivity: list[SensitivityScenario]
    approval_tier_required: ApprovalTier
    rationale_narrative: str
    computed_at: str = field(default_factory=now_iso)


# ════════════════════════════════════════════════════════════════════
# S07 — Operating model
# ════════════════════════════════════════════════════════════════════

@dataclass
class NamedRole:
    role: str
    location: str
    named_person: str = "tbd"


@dataclass
class GovernanceForum:
    forum: str
    cadence: str
    participants: list[str]


@dataclass
class ServiceModelLayer:
    model: Literal["dedicated", "hybrid", "pooled"]
    named_roles: list[NamedRole]
    governance_cadence: list[GovernanceForum]
    escalation_path: list[str] = field(default_factory=list)


@dataclass
class FunctionalFootprint:
    function: str
    primary_location: str
    follow_the_sun: list[str] = field(default_factory=list)


@dataclass
class HireRequisition:
    role: str
    location: str
    count: float
    hiring_start: str
    hiring_lead_time_weeks: int
    transition_risk: Literal["low", "medium", "high"] = "low"


@dataclass
class FteYearPlan:
    year: int
    net_new_hires: list[HireRequisition]
    redeployment_count: float
    total_fte: float


@dataclass
class TransitionMilestone:
    milestone: str
    target_date: str
    dependencies: list[str] = field(default_factory=list)


@dataclass
class FtePlan:
    by_year: list[FteYearPlan]
    parallel_running_weeks: int
    parallel_running_fte_overhead: float
    transition_milestones: list[TransitionMilestone]


@dataclass
class AppImpactSummary:
    app_id: str
    scope_role: str
    capacity_action: str
    go_live_dependency: bool


@dataclass
class IntegrationBuild:
    integration: str
    build_weeks: int
    owner: str


@dataclass
class ReportingBuild:
    report: str
    build_weeks: int
    owner: str


@dataclass
class RtoRpoCommitment:
    service: str
    rto_hours: int
    rpo_minutes: int
    ddq_commitment_ref: Optional[str] = None


@dataclass
class ResiliencePosture:
    bcp_coverage_per_location: list[str]
    single_points_of_failure_added: list[str]
    rto_rpo_commitments: list[RtoRpoCommitment]


@dataclass
class ControlEnvironmentChanges:
    new_controls: list[str]
    extended_controls: list[str]
    soc_scope_change_required: bool
    soc_scope_change_cost_usd: int
    audit_readiness_milestone: str


@dataclass
class CommitmentCrosscheck:
    commitment_id: CommitmentId
    met_by: Optional[str]
    status: Literal["met", "unmet", "amended"]


@dataclass
class OperatingModelPlan:
    operating_model_id: OperatingModelId
    opportunity_id: OpportunityId
    client_service_layer: ServiceModelLayer
    operational_footprint: list[FunctionalFootprint]
    fte_plan: FtePlan
    app_impact: list[AppImpactSummary]
    integration_builds: list[IntegrationBuild]
    reporting_builds: list[ReportingBuild]
    resilience_posture: ResiliencePosture
    control_environment: ControlEnvironmentChanges
    ddq_commitment_crosscheck: list[CommitmentCrosscheck]
    computed_at: str = field(default_factory=now_iso)

    @property
    def has_unmet_commitments(self) -> bool:
        return any(c.status == "unmet" for c in self.ddq_commitment_crosscheck)


# ════════════════════════════════════════════════════════════════════
# S08 — Approval, deal journal, sealed bundle
# ════════════════════════════════════════════════════════════════════

ApprovalDecision = Literal["approved", "rejected", "pending"]


@dataclass
class Approver:
    role: str
    user_id: str
    ts: str
    signature: str
    comment: str = ""


@dataclass
class ApprovalRequest:
    request_id: ApprovalRequestId
    opportunity_id: OpportunityId
    tier_required: ApprovalTier
    approvers_required: list[str]
    decisions: list[Approver] = field(default_factory=list)
    state: Literal["open", "approved", "rejected"] = "open"
    created_at: str = field(default_factory=now_iso)


JournalKind = Literal[
    "intake", "resolve", "scope", "ddq.link", "ddq.commitment",
    "complexity.score", "cost.compute", "capacity.analyze",
    "pricing.propose", "operating_model.design",
    "approval.request", "approval.decision", "override",
    "seal", "handoff", "actuals.update",
    "source.promote", "disposition", "advance",
]


@dataclass
class DealJournalEvent:
    event_id: str
    opportunity_id: OpportunityId
    deal_id: Optional[DealId]
    actor_kind: Literal["user", "system"]
    actor_id: str
    actor_role: str
    kind: JournalKind
    ts: str
    payload: dict
    payload_hash: str
    prev_hash: str
    chain_hash: str


@dataclass
class SealedDealBundle:
    deal_id: DealId
    opportunity_id: OpportunityId
    sealed_at: str
    ucm_snapshot_version: str
    upm_snapshot_version: str
    ddq_run_ids: list[str]
    scope_manifest_hash: str
    complexity_scorecard_hash: str
    cost_stack_hash: str
    capacity_impact_hash: str
    pricing_proposal_hash: str
    operating_model_plan_hash: str
    commitment_set_hash: str
    approval_chain: list[Approver]
    merkle_root: str
    platform_version: str
    handoff_targets: list[str]


# ════════════════════════════════════════════════════════════════════
# eCRM sourceable prospects — pre-opportunity inbound feed
# ════════════════════════════════════════════════════════════════════
# These represent inbound items from the various S01 channels (RFP email,
# RM-submitted via eCRM, consultant-driven, cross-segment referral, retender)
# *before* they are promoted into a control-plane Opportunity. A one-click
# promote operation creates a full Opportunity from the source's fields.

EcrmSourceState = Literal["new", "triaging", "promoted", "declined"]


@dataclass
class EcrmSource:
    source_id: str
    ecrm_id: str                                # mirrored Salesforce id
    received_at: str
    channel: Literal["rfp_email", "rm_submitted", "consultant", "cross_segment", "retender"]
    consultant: Optional[str] = None
    headline: str = ""                          # short summary, e.g. "Acme Pension EU — Global Custody RFP"
    prospect_legal_name: str = ""
    prospect_domicile: str = ""
    client_segment: ClientSegment = "asset_manager"
    ucm_id: Optional[str] = None                # null = new entity (KYC kickoff)
    rm_user_id: Optional[str] = None
    exec_sponsor_user_id: Optional[str] = None
    products_requested: list[str] = field(default_factory=list)
    jurisdictions: list[str] = field(default_factory=list)
    estimated_aum_usd: int = 0
    indicative_go_live: Optional[str] = None
    nav_strikes_per_day: int = 0
    transactions_per_year: int = 0
    capital_events_per_year: int = 0
    shareholders: int = 0
    raw_artifacts: list[str] = field(default_factory=list)
    existing_revenue_usd_annual: int = 0
    existing_products: list[str] = field(default_factory=list)
    cross_sell_pipeline: list[str] = field(default_factory=list)
    entity_tree_roles: list[EntityTreeRole] = field(default_factory=list)
    notes: str = ""
    state: EcrmSourceState = "new"
    promoted_opportunity_id: Optional[str] = None
    promoted_at: Optional[str] = None
