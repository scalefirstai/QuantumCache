// Domain types for the Asset Servicing Opportunity-to-Deal platform.
// Mirrors core/domain/opp_deal.py — keep these two in sync.

export type OpportunityStatus =
  | "intake"
  | "resolving"
  | "scoping"
  | "ddq"
  | "complexity"
  | "cost_capacity"
  | "pricing"
  | "operating_model"
  | "approval"
  | "won"
  | "lost"
  | "withdrawn";

export type ClientSegment =
  | "asset_manager"
  | "asset_owner_pension"
  | "sovereign"
  | "insurance"
  | "alts_manager";

export type IntakeChannel =
  | "rfp_email"
  | "rm_submitted"
  | "consultant"
  | "cross_segment"
  | "retender";

export type ComplexityTier =
  | "T1_low"
  | "T2_standard"
  | "T3_high"
  | "T4_exceptional";

export type ApprovalTier =
  | "tier_1_rm_segment_head"
  | "tier_2_segment_head_cfo_delegate"
  | "tier_3_cfo_coo_risk"
  | "tier_4_segment_ceo_cfo";

export type CapacityVerdict =
  | "fits_in_headroom"
  | "expansion_required"
  | "declining_risk";

export type CommitmentClass =
  | "sla"
  | "control"
  | "jurisdiction_coverage"
  | "data_residency"
  | "reporting"
  | "other";

export type ScopeIssueSeverity = "info" | "warn" | "blocking";

export interface EntityTreeRole {
  role: string;
  ucm_id: string;
  label: string;
}

export interface ClientResolution {
  ucm_id: string | null;
  ucm_snapshot_version: string;
  legal_name: string;
  domicile: string;
  client_segment: ClientSegment;
  entity_tree_roles: EntityTreeRole[];
  kyc_status: string;
  confidence: number;
}

export interface IntakeSource {
  channel: IntakeChannel;
  consultant: string | null;
  received_at: string;
  raw_artifacts: string[];
}

export interface RelationshipContext {
  existing_revenue_usd_annual: number;
  existing_products: string[];
  cross_sell_pipeline: string[];
  at_risk_competitor_clients: string[];
  rm_user_id: string | null;
  exec_sponsor_user_id: string | null;
}

export interface ScopeSummary {
  products_requested: string[];
  jurisdictions: string[];
  estimated_aum_usd: number;
  indicative_go_live: string | null;
  nav_strikes_per_day: number;
  transactions_per_year: number;
  capital_events_per_year: number;
  shareholders: number;
}

export interface Opportunity {
  opportunity_id: string;
  ecrm_id: string;
  status: OpportunityStatus;
  name: string;
  source: IntakeSource;
  client: ClientResolution;
  relationship: RelationshipContext;
  scope_summary: ScopeSummary;
  ddq_run_id: string | null;
  scope_manifest_id: string | null;
  complexity_id: string | null;
  cost_stack_id: string | null;
  capacity_id: string | null;
  pricing_id: string | null;
  operating_model_id: string | null;
  deal_id: string | null;
  disposition_reason: string | null;
  disposition_at: string | null;
  source_id: string | null;
  created_at: string;
  updated_at: string;
}

export type EcrmSourceState = "new" | "triaging" | "promoted" | "declined";

export interface EcrmSource {
  source_id: string;
  ecrm_id: string;
  received_at: string;
  channel: IntakeChannel;
  consultant: string | null;
  headline: string;
  prospect_legal_name: string;
  prospect_domicile: string;
  client_segment: ClientSegment;
  ucm_id: string | null;
  rm_user_id: string | null;
  exec_sponsor_user_id: string | null;
  products_requested: string[];
  jurisdictions: string[];
  estimated_aum_usd: number;
  indicative_go_live: string | null;
  nav_strikes_per_day: number;
  transactions_per_year: number;
  capital_events_per_year: number;
  shareholders: number;
  raw_artifacts: string[];
  existing_revenue_usd_annual: number;
  existing_products: string[];
  cross_sell_pipeline: string[];
  entity_tree_roles: EntityTreeRole[];
  notes: string;
  state: EcrmSourceState;
  promoted_opportunity_id: string | null;
  promoted_at: string | null;
}

export interface DeliveryStackEntry {
  app_id: string;
  role: string;
  load_factor: string;
}

export interface ScopeLineItem {
  upm_code: string;
  label: string;
  jurisdiction: string;
  legal_entity: string;
  delivery_stack: DeliveryStackEntry[];
  dependencies: string[];
}

export interface ScopeIssue {
  severity: ScopeIssueSeverity;
  code: string;
  message: string;
  upm_code: string | null;
}

export interface ScopeManifest {
  scope_manifest_id: string;
  opportunity_id: string;
  upm_snapshot_version: string;
  line_items: ScopeLineItem[];
  legal_entity_assignment: Record<string, string>;
  derived_app_set: string[];
  derived_jurisdictions: string[];
  issues: ScopeIssue[];
  created_at: string;
}

export interface ComplexityDimension {
  key: string;
  score: number;
  notes: string;
}

export interface ComplexityScorecard {
  complexity_id: string;
  opportunity_id: string;
  scorecard_version: string;
  dimensions: ComplexityDimension[];
  weights: Record<string, number>;
  composite_score: number;
  tier: ComplexityTier;
  rationale_narrative: string;
  scored_at: string;
  scored_by: string;
}

export interface FteLine {
  function: string;
  location: string;
  role: string;
  count: number;
  fully_loaded_rate_usd: number;
  year: number;
}

export interface SubCustodyLine {
  market: string;
  annual_usd: number;
}

export interface TechRunCostLine {
  app_id: string;
  annual_usd: number;
  basis: string;
}

export interface TechExpansionLine {
  app_id: string;
  expansion_cost_usd: number;
  one_time: boolean;
  lead_time_weeks: number;
}

export interface TransitionOneTime {
  implementation_fte_usd: number;
  parallel_running_usd: number;
  data_migration_usd: number;
  client_integration_build_usd: number;
}

export interface RiskComplianceLine {
  function: string;
  annual_usd: number;
}

export interface CostStack {
  cost_stack_id: string;
  opportunity_id: string;
  horizon_years: number;
  direct_fte: FteLine[];
  sub_custody_passthrough: SubCustodyLine[];
  technology_run_cost: TechRunCostLine[];
  technology_capacity_expansion: TechExpansionLine[];
  transition_one_time: TransitionOneTime;
  risk_compliance_overhead: RiskComplianceLine[];
  allocated_overhead_pct: number;
  totals: {
    year_1_total_usd: number;
    year_2_total_usd: number;
    year_3_total_usd: number;
    five_year_npv_usd: number;
  };
  computed_at: string;
}

export interface AppImpact {
  app_id: string;
  label: string;
  projected_delta: Record<string, number>;
  post_deal_utilization_pct: Record<string, number>;
  verdict: CapacityVerdict;
  recommended_action: string;
  expansion_cost_usd: number;
  lead_time_weeks: number;
}

export interface BlockingConstraint {
  app_id: string;
  constraint: string;
  severity: "low" | "medium" | "high";
}

export interface CapacityImpact {
  capacity_impact_id: string;
  opportunity_id: string;
  app_impacts: AppImpact[];
  blocking_constraints: BlockingConstraint[];
  computed_at: string;
}

export interface PricingProposal {
  pricing_proposal_id: string;
  opportunity_id: string;
  fee_structure: {
    asset_based: Array<{
      asset_class: string;
      tiers: Array<{
        aum_band_usd_min: number;
        aum_band_usd_max: number;
        bp: number;
      }>;
    }>;
    transactional: Array<{ event: string; fee_usd: number }>;
    fixed_retainers: Array<{ service: string; annual_usd: number }>;
    passthrough_oop: string[];
    minimum_fee_floor_usd_annual: number;
    term_years: number;
    term_discount_pct: number;
    bundled_discount_pct: number;
  };
  sec_lending: { client_pct: number; bny_pct: number };
  fx_revenue: { standing_instruction_margin_bp: number; disclosure_class: string };
  total_client_value: {
    by_year: Array<{
      year: number;
      direct_fee_usd: number;
      sec_lending_revenue_usd: number;
      fx_revenue_usd: number;
      nii_on_balances_usd: number;
      adjacent_revenue_usd: number;
    }>;
    five_year_total_usd: number;
  };
  margin_analysis: {
    year_1_direct_margin_pct: number;
    year_1_total_margin_pct: number;
    five_year_npv_usd: number;
    irr_pct: number;
    payback_years: number;
  };
  sensitivity: Array<{
    scenario: string;
    year_1_margin_pct_delta: number;
    five_year_npv_usd: number;
  }>;
  approval_tier_required: ApprovalTier;
  rationale_narrative: string;
  computed_at: string;
}

export interface Commitment {
  commitment_id: string;
  opportunity_id: string;
  ddq_run_id: string;
  canonical_id: string;
  library_entry_hash: string;
  commitment_text: string;
  commitment_class: CommitmentClass;
  material: boolean;
  contract_schedule_target: string;
  status: string;
  extracted_at: string;
}

export interface CommitmentSet {
  opportunity_id: string;
  ddq_run_id: string | null;
  commitments: Commitment[];
}

export interface NamedRole {
  role: string;
  location: string;
  named_person: string;
}

export interface GovernanceForum {
  forum: string;
  cadence: string;
  participants: string[];
}

export interface HireRequisition {
  role: string;
  location: string;
  count: number;
  hiring_start: string;
  hiring_lead_time_weeks: number;
  transition_risk: "low" | "medium" | "high";
}

export interface FteYearPlan {
  year: number;
  net_new_hires: HireRequisition[];
  redeployment_count: number;
  total_fte: number;
}

export interface CommitmentCrosscheck {
  commitment_id: string;
  met_by: string | null;
  status: "met" | "unmet" | "amended";
}

export interface OperatingModelPlan {
  operating_model_id: string;
  opportunity_id: string;
  client_service_layer: {
    model: "dedicated" | "hybrid" | "pooled";
    named_roles: NamedRole[];
    governance_cadence: GovernanceForum[];
    escalation_path: string[];
  };
  operational_footprint: Array<{
    function: string;
    primary_location: string;
    follow_the_sun: string[];
  }>;
  fte_plan: {
    by_year: FteYearPlan[];
    parallel_running_weeks: number;
    parallel_running_fte_overhead: number;
    transition_milestones: Array<{
      milestone: string;
      target_date: string;
      dependencies: string[];
    }>;
  };
  app_impact: Array<{
    app_id: string;
    scope_role: string;
    capacity_action: string;
    go_live_dependency: boolean;
  }>;
  integration_builds: Array<{ integration: string; build_weeks: number; owner: string }>;
  reporting_builds: Array<{ report: string; build_weeks: number; owner: string }>;
  resilience_posture: {
    bcp_coverage_per_location: string[];
    single_points_of_failure_added: string[];
    rto_rpo_commitments: Array<{
      service: string;
      rto_hours: number;
      rpo_minutes: number;
      ddq_commitment_ref: string | null;
    }>;
  };
  control_environment: {
    new_controls: string[];
    extended_controls: string[];
    soc_scope_change_required: boolean;
    soc_scope_change_cost_usd: number;
    audit_readiness_milestone: string;
  };
  ddq_commitment_crosscheck: CommitmentCrosscheck[];
  computed_at: string;
}

export interface Approver {
  role: string;
  user_id: string;
  ts: string;
  signature: string;
  comment: string;
}

export interface ApprovalRequest {
  request_id: string;
  opportunity_id: string;
  tier_required: ApprovalTier;
  approvers_required: string[];
  decisions: Approver[];
  state: "open" | "approved" | "rejected";
  created_at: string;
}

export interface SealedDealBundle {
  deal_id: string;
  opportunity_id: string;
  sealed_at: string;
  ucm_snapshot_version: string;
  upm_snapshot_version: string;
  ddq_run_ids: string[];
  scope_manifest_hash: string;
  complexity_scorecard_hash: string;
  cost_stack_hash: string;
  capacity_impact_hash: string;
  pricing_proposal_hash: string;
  operating_model_plan_hash: string;
  commitment_set_hash: string;
  approval_chain: Approver[];
  merkle_root: string;
  platform_version: string;
  handoff_targets: string[];
}

export interface ReplayReport {
  ok: boolean;
  deal_id?: string;
  reason?: string;
  checks?: Record<string, boolean>;
  merkle_root?: string;
}

export interface DealJournalEvent {
  event_id: string;
  opportunity_id: string;
  deal_id: string | null;
  actor_kind: "user" | "system";
  actor_id: string;
  actor_role: string;
  kind: string;
  ts: string;
  payload: Record<string, unknown>;
  payload_hash: string;
  prev_hash: string;
  chain_hash: string;
}

export interface UpmEntry {
  upm_code: string;
  label: string;
  eligible_jurisdictions: string[];
  delivery_stack: DeliveryStackEntry[];
  dependencies: string[];
  legal_entities: string[];
  status: string;
}

export const STAGE_IDS = ["S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08"] as const;
export type StageId = (typeof STAGE_IDS)[number];

export const STAGE_LABELS: Record<StageId, string> = {
  S01: "Intake",
  S02: "Scope",
  S03: "DDQ",
  S04: "Complexity",
  S05: "Cost + Capacity",
  S06: "Pricing",
  S07: "Operating model",
  S08: "Approval + seal",
};

// Each stage is owned by a specific team. The workspace surfaces this so the
// user can see where a deal is in the lifecycle and which partner team owns
// the next decision. Codes from spec are kept as secondary metadata.
export type StageOwner =
  | "Deal team"
  | "DDQ team"
  | "Cost engineering"
  | "Pricing committee"
  | "Operations design"
  | "Approval committee";

export interface StageMeta {
  id: StageId;
  shortLabel: string;          // plain-English primary label
  fullLabel: string;           // long form for headers
  owner: StageOwner;
  blurb: string;               // one-line description of what happens here
}

export const STAGE_META: Record<StageId, StageMeta> = {
  S01: {
    id: "S01",
    shortLabel: "Intake",
    fullLabel: "Intake & client resolution",
    owner: "Deal team",
    blurb: "Inbound RFP captured; UCM entity tree resolved.",
  },
  S02: {
    id: "S02",
    shortLabel: "Scope",
    fullLabel: "Product scope (UPM)",
    owner: "Deal team",
    blurb: "Products resolved to UPM with delivery-app stack and legal-entity routing.",
  },
  S03: {
    id: "S03",
    shortLabel: "DDQ",
    fullLabel: "Due diligence commitments",
    owner: "DDQ team",
    blurb: "DDQ run drives material commitments that flow into the contract.",
  },
  S04: {
    id: "S04",
    shortLabel: "Complexity",
    fullLabel: "Complexity scorecard",
    owner: "Deal team",
    blurb: "10-dimension scorecard sets approval routing and review depth.",
  },
  S05: {
    id: "S05",
    shortLabel: "Cost + Capacity",
    fullLabel: "Cost stack & technology capacity",
    owner: "Cost engineering",
    blurb: "FTE + sub-custody + tech run cost; app utilization impact analysed.",
  },
  S06: {
    id: "S06",
    shortLabel: "Pricing",
    fullLabel: "Pricing & total client value",
    owner: "Pricing committee",
    blurb: "Fee structure with TCV: direct fee + sec lending + FX + NII + adjacent.",
  },
  S07: {
    id: "S07",
    shortLabel: "Operating model",
    fullLabel: "Operating model & FTE plan",
    owner: "Operations design",
    blurb: "Service model, hiring plan, resilience and DDQ commitment cross-check.",
  },
  S08: {
    id: "S08",
    shortLabel: "Approval & seal",
    fullLabel: "Tier-gated approval & sealed deal bundle",
    owner: "Approval committee",
    blurb: "Required approver chain; on full sign-off the deal bundle is sealed.",
  },
};

export const OWNER_TONE: Record<StageOwner, string> = {
  "Deal team": "bg-bny-teal/10 text-bny-teal border-bny-teal/30",
  "DDQ team": "bg-bny-ochre/10 text-bny-ochre border-bny-ochre/30",
  "Cost engineering": "bg-bny-ink/10 text-bny-ink border-bny-ink/20",
  "Pricing committee": "bg-bny-ok/10 text-bny-ok border-bny-ok/30",
  "Operations design": "bg-bny-ink/10 text-bny-ink border-bny-ink/20",
  "Approval committee": "bg-bny-danger/10 text-bny-danger border-bny-danger/30",
};
