"""
Filesystem-backed adapter for the Opp→Deal platform.

In-memory + JSON-on-disk implementation that fronts every stage repo,
every deterministic numeric engine, and the deal journal. Production
wires Mongo + S3 + the real BNY systems behind the same protocols in
`core/ports/opp_deal.py`.

Storage layout under $manifests_dir/opp-deal/:
  opportunities.json, scopes.json, complexity.json, cost.json,
  capacity.json, pricing.json, operating-models.json,
  commitments.json, approvals.json, journal.json,
  sealed/<deal_id>.json, upm.json

Numeric engines (cost, capacity, pricing) are deterministic — same
inputs → byte-identical outputs. LLM-drafted narratives are stubbed
locally so the build runs without API keys.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from core.domain.opp_deal import (
    ApprovalRequest,
    ApprovalTier,
    AppImpact,
    AppImpactSummary,
    Approver,
    AssetBandFee,
    AssetBasedTier,
    BlockingConstraint,
    CapacityImpact,
    Commitment,
    CommitmentCrosscheck,
    CommitmentSet,
    COMPLEXITY_DIMENSIONS,
    ComplexityDimensionScore,
    ComplexityScorecard,
    ControlEnvironmentChanges,
    CostStack,
    CostTotals,
    DealJournalEvent,
    DeliveryStackEntry,
    EcrmSource,
    EntityTreeRole,
    FeeStructure,
    FixedRetainer,
    FteLine,
    FtePlan,
    FteYearPlan,
    FunctionalFootprint,
    FxRevenueModel,
    GovernanceForum,
    HireRequisition,
    IntakeSource,
    IntegrationBuild,
    MarginAnalysis,
    NamedRole,
    OperatingModelPlan,
    Opportunity,
    OpportunityId,
    PricingProposal,
    ClientResolution,
    RelationshipContext,
    ReportingBuild,
    ResiliencePosture,
    RiskComplianceLine,
    RtoRpoCommitment,
    ScopeIssue,
    ScopeLineItem,
    ScopeManifest,
    ScopeSummary,
    SealedDealBundle,
    SecLendingShare,
    SensitivityScenario,
    ServiceModelLayer,
    SubCustodyLine,
    TechExpansionLine,
    TechRunCostLine,
    TotalClientValue,
    TotalClientValueYear,
    TransitionMilestone,
    TransitionOneTime,
    merkle_root,
    now_iso,
    payload_hash,
)


_PLATFORM_VERSION = "v0.1.0"


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=_json_default, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _json_default(o: Any) -> Any:
    if is_dataclass(o):
        return asdict(o)
    raise TypeError(f"object of type {type(o).__name__} is not JSON serializable")


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _ulid() -> str:
    return uuid.uuid4().hex[:12]


# ════════════════════════════════════════════════════════════════════
# UPM catalog — read-only seed
# ════════════════════════════════════════════════════════════════════

UPM_CATALOG: dict[str, dict] = {
    "custody.global": {
        "label": "Global Custody",
        "eligible_jurisdictions": ["IE", "LU", "US", "KY", "SG", "HK", "UK", "JP"],
        "delivery_stack": [
            {"app_id": "app.gss.prod", "role": "primary_custody", "load_factor": "per_holding"},
            {"app_id": "app.eagle_pace.prod", "role": "data_layer", "load_factor": "per_holding"},
            {"app_id": "app.nexen.prod", "role": "client_portal", "load_factor": "per_user"},
        ],
        "dependencies": [],
        "legal_entities": ["bny_mellon_sa_nv", "bny_mellon_london_branch", "bny_mellon_ny"],
        "status": "active",
    },
    "fa.daily_nav": {
        "label": "Daily NAV Fund Accounting",
        "eligible_jurisdictions": ["IE", "LU", "US", "KY", "SG", "HK", "UK"],
        "delivery_stack": [
            {"app_id": "app.invest_one.prod", "role": "primary_accounting", "load_factor": "per_nav_strike"},
            {"app_id": "app.eagle_pace.prod", "role": "data_layer", "load_factor": "per_holding"},
            {"app_id": "app.nexen.prod", "role": "client_portal", "load_factor": "per_user"},
        ],
        "dependencies": ["custody.global"],
        "legal_entities": ["bny_fund_services_ireland", "bny_mellon_sa_nv"],
        "status": "active",
    },
    "fa.multi_class": {
        "label": "Multi-class NAV Fund Accounting",
        "eligible_jurisdictions": ["IE", "LU"],
        "delivery_stack": [
            {"app_id": "app.invest_one.prod", "role": "primary_accounting", "load_factor": "per_nav_strike"},
        ],
        "dependencies": ["fa.daily_nav"],
        "legal_entities": ["bny_fund_services_ireland", "bny_mellon_sa_nv"],
        "status": "active",
    },
    "fadmin.regulatory_reporting.ucits": {
        "label": "UCITS Regulatory Reporting",
        "eligible_jurisdictions": ["IE", "LU"],
        "delivery_stack": [
            {"app_id": "app.regreporting.prod", "role": "reporting", "load_factor": "per_filing"},
        ],
        "dependencies": ["fa.daily_nav"],
        "legal_entities": ["bny_fund_services_ireland", "bny_mellon_sa_nv"],
        "status": "active",
    },
    "ta.lux": {
        "label": "Luxembourg Transfer Agency",
        "eligible_jurisdictions": ["LU"],
        "delivery_stack": [
            {"app_id": "app.iss.prod", "role": "transfer_agency", "load_factor": "per_shareholder"},
        ],
        "dependencies": [],
        "legal_entities": ["bny_mellon_sa_nv"],
        "status": "active",
    },
    "ta.dublin": {
        "label": "Dublin Transfer Agency",
        "eligible_jurisdictions": ["IE"],
        "delivery_stack": [
            {"app_id": "app.iss.prod", "role": "transfer_agency", "load_factor": "per_shareholder"},
        ],
        "dependencies": [],
        "legal_entities": ["bny_fund_services_ireland"],
        "status": "active",
    },
    "depo.ucits": {
        "label": "UCITS Depositary",
        "eligible_jurisdictions": ["IE", "LU"],
        "delivery_stack": [
            {"app_id": "app.depo.prod", "role": "depositary", "load_factor": "per_holding"},
        ],
        "dependencies": ["custody.global"],
        "legal_entities": ["bny_fund_services_ireland", "bny_mellon_sa_nv"],
        "status": "active",
    },
    "depo.aifmd": {
        "label": "AIFMD Depositary",
        "eligible_jurisdictions": ["IE", "LU"],
        "delivery_stack": [
            {"app_id": "app.depo.prod", "role": "depositary", "load_factor": "per_holding"},
        ],
        "dependencies": ["custody.global"],
        "legal_entities": ["bny_fund_services_ireland", "bny_mellon_sa_nv"],
        "status": "active",
    },
    "alts.pe_admin": {
        "label": "Private Equity Fund Administration",
        "eligible_jurisdictions": ["IE", "LU", "KY", "US"],
        "delivery_stack": [
            {"app_id": "app.investran.prod", "role": "pe_admin", "load_factor": "per_capital_event"},
        ],
        "dependencies": [],
        "legal_entities": ["bny_mellon_sa_nv", "bny_fund_services_ireland"],
        "status": "active",
    },
    "moo.ibor": {
        "label": "Investment Book of Record (Middle Office)",
        "eligible_jurisdictions": ["IE", "LU", "US", "UK"],
        "delivery_stack": [
            {"app_id": "app.eagle_pace.prod", "role": "ibor", "load_factor": "per_holding"},
        ],
        "dependencies": [],
        "legal_entities": ["bny_mellon_ny", "bny_mellon_sa_nv"],
        "status": "active",
    },
    "seclen.agency": {
        "label": "Agency Securities Lending",
        "eligible_jurisdictions": ["IE", "LU", "US", "UK"],
        "delivery_stack": [
            {"app_id": "app.seclen.prod", "role": "agency_lending", "load_factor": "per_position"},
        ],
        "dependencies": ["custody.global"],
        "legal_entities": ["bny_mellon_ny", "bny_mellon_london_branch"],
        "status": "active",
    },
    "fx.standing_instruction": {
        "label": "Standing Instruction FX",
        "eligible_jurisdictions": ["IE", "LU", "US", "UK", "SG"],
        "delivery_stack": [
            {"app_id": "app.fx.prod", "role": "fx_si", "load_factor": "per_trade"},
        ],
        "dependencies": [],
        "legal_entities": ["bny_mellon_ny", "bny_mellon_london_branch"],
        "status": "active",
    },
    "conn.nexen_portal": {
        "label": "NEXEN Client Portal",
        "eligible_jurisdictions": ["IE", "LU", "US", "UK", "SG"],
        "delivery_stack": [
            {"app_id": "app.nexen.prod", "role": "client_portal", "load_factor": "per_user"},
        ],
        "dependencies": [],
        "legal_entities": ["bny_mellon_ny"],
        "status": "active",
    },
}


# ════════════════════════════════════════════════════════════════════
# App registry — capacity envelopes (S05b inputs)
# ════════════════════════════════════════════════════════════════════

APP_REGISTRY: dict[str, dict] = {
    "app.gss.prod": {
        "label": "Global Sub-Custody System",
        "domain": "custody",
        "capacity": {"holdings": 12_000_000, "current": 9_400_000, "trades_per_day": 850_000, "trades_per_day_current": 620_000},
        "expansion": {"step": "scale_out_compute", "delta_pct": 25, "cost_usd": 620_000, "lead_time_weeks": 14},
        "load_per_unit": {"per_holding": {"holdings": 1.0}, "per_trade": {"trades_per_day": 1.0}},
    },
    "app.invest_one.prod": {
        "label": "InvestOne Production",
        "domain": "fund_accounting",
        "capacity": {"nav_strikes_per_day": 4200, "nav_strikes_per_day_current": 3650, "storage_tb": 480, "storage_tb_current": 412},
        "expansion": {"step": "scale_out_compute", "delta_pct": 25, "cost_usd": 450_000, "lead_time_weeks": 12},
        "load_per_unit": {"per_nav_strike": {"nav_strikes_per_day": 1.0, "storage_tb": 0.018}},
    },
    "app.eagle_pace.prod": {
        "label": "Eagle PACE",
        "domain": "data",
        "capacity": {"holdings": 25_000_000, "current": 19_200_000, "downstream_consumers": 18, "downstream_consumers_current": 14},
        "expansion": {"step": "shared_pool_extend", "delta_pct": 20, "cost_usd": 380_000, "lead_time_weeks": 10},
        "load_per_unit": {"per_holding": {"holdings": 1.0}},
    },
    "app.nexen.prod": {
        "label": "NEXEN Portal",
        "domain": "client",
        "capacity": {"users": 95_000, "users_current": 71_000, "api_qps": 4500, "api_qps_current": 3100},
        "expansion": {"step": "horizontal_scale", "delta_pct": 30, "cost_usd": 210_000, "lead_time_weeks": 6},
        "load_per_unit": {"per_user": {"users": 1.0}},
    },
    "app.iss.prod": {
        "label": "Investor Servicing System",
        "domain": "ta",
        "capacity": {"shareholders": 4_500_000, "shareholders_current": 3_650_000},
        "expansion": {"step": "scale_out_compute", "delta_pct": 25, "cost_usd": 285_000, "lead_time_weeks": 9},
        "load_per_unit": {"per_shareholder": {"shareholders": 1.0}},
    },
    "app.regreporting.prod": {
        "label": "Regulatory Reporting Platform",
        "domain": "reg",
        "capacity": {"filings_per_month": 8500, "filings_per_month_current": 6200},
        "expansion": {"step": "scale_out_compute", "delta_pct": 20, "cost_usd": 175_000, "lead_time_weeks": 8},
        "load_per_unit": {"per_filing": {"filings_per_month": 1.0}},
    },
    "app.depo.prod": {
        "label": "Depositary Oversight Platform",
        "domain": "depo",
        "capacity": {"holdings": 6_500_000, "holdings_current": 5_100_000},
        "expansion": {"step": "scale_out_compute", "delta_pct": 25, "cost_usd": 240_000, "lead_time_weeks": 10},
        "load_per_unit": {"per_holding": {"holdings": 1.0}},
    },
    "app.investran.prod": {
        "label": "Investran PE Admin",
        "domain": "alts",
        "capacity": {"capital_events_per_year": 22_000, "capital_events_per_year_current": 16_500},
        "expansion": {"step": "scale_out_compute", "delta_pct": 30, "cost_usd": 195_000, "lead_time_weeks": 10},
        "load_per_unit": {"per_capital_event": {"capital_events_per_year": 1.0}},
    },
    "app.seclen.prod": {
        "label": "Agency Securities Lending Platform",
        "domain": "seclen",
        "capacity": {"positions": 2_400_000, "positions_current": 1_810_000},
        "expansion": {"step": "scale_out_compute", "delta_pct": 25, "cost_usd": 165_000, "lead_time_weeks": 9},
        "load_per_unit": {"per_position": {"positions": 1.0}},
    },
    "app.fx.prod": {
        "label": "Standing Instruction FX Engine",
        "domain": "fx",
        "capacity": {"trades_per_day": 95_000, "trades_per_day_current": 71_500},
        "expansion": {"step": "scale_out_compute", "delta_pct": 25, "cost_usd": 145_000, "lead_time_weeks": 8},
        "load_per_unit": {"per_trade": {"trades_per_day": 1.0}},
    },
}


# ════════════════════════════════════════════════════════════════════
# Role-rate catalogue and location strategy (S05a inputs)
# ════════════════════════════════════════════════════════════════════

ROLE_RATES: dict[tuple[str, str], int] = {
    # (role, location) → fully-loaded annual USD
    ("fa_specialist_l2", "lux"): 145_000,
    ("fa_specialist_l2", "dublin"): 132_000,
    ("fa_specialist_l2", "pune"): 38_000,
    ("ca_specialist_l1", "pune"): 32_000,
    ("ca_specialist_l1", "manchester"): 78_000,
    ("ca_specialist_l1", "ny"): 110_000,
    ("client_service_director", "ny"): 285_000,
    ("client_service_director", "lux"): 240_000,
    ("client_service_director", "london"): 260_000,
    ("client_service_manager", "lux"): 165_000,
    ("ta_specialist", "lux"): 110_000,
    ("ta_specialist", "dublin"): 98_000,
    ("alts_admin_specialist", "ny"): 165_000,
    ("alts_admin_specialist", "lux"): 145_000,
    ("depo_controller", "dublin"): 158_000,
    ("depo_controller", "lux"): 168_000,
    ("middle_office_l1", "pune"): 36_000,
    ("middle_office_l2", "manchester"): 92_000,
    ("regulatory_reporter", "dublin"): 118_000,
    ("regulatory_reporter", "lux"): 128_000,
    ("aml_kyc_analyst", "pune"): 34_000,
    ("seclending_trader", "ny"): 220_000,
    ("seclending_trader", "london"): 215_000,
    ("hiring_lead_time_weeks", "*"): 16,  # NB: not a rate; queried by FTE planner
}

LOCATION_HIRING_WEEKS: dict[str, int] = {
    "lux": 18, "dublin": 16, "ny": 14, "london": 14,
    "pune": 8, "manchester": 12, "singapore": 16, "hong_kong": 16,
}

# Location strategy: which functions can run where.
LOCATION_STRATEGY: dict[str, set[str]] = {
    "fund_accounting": {"lux", "dublin", "pune"},
    "custody_corp_actions": {"pune", "manchester", "ny"},
    "transfer_agency": {"lux", "dublin"},
    "depositary": {"dublin", "lux"},
    "client_service": {"ny", "lux", "london"},
    "alts_admin": {"ny", "lux"},
    "middle_office": {"pune", "manchester", "ny"},
    "regulatory_reporting": {"dublin", "lux"},
    "aml_kyc": {"pune", "manchester"},
    "seclending": {"ny", "london"},
}


SUB_CUSTODY_RATES: dict[str, int] = {
    "US": 25_000, "UK": 28_000, "DE": 32_000, "FR": 30_000,
    "IE": 24_000, "LU": 22_000, "JP": 58_000, "SG": 48_000,
    "HK": 55_000, "BR": 280_000, "NG": 95_000, "IN": 110_000,
    "CN": 145_000, "ZA": 78_000, "MX": 65_000,
}


# ════════════════════════════════════════════════════════════════════
# Adapter
# ════════════════════════════════════════════════════════════════════

class FsOppDeal:
    """One adapter implements every Opp→Deal port + deterministic engines."""

    def __init__(self, manifests_dir: Path) -> None:
        self._base = manifests_dir / "opp-deal"
        self._base.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._files = {
            "opportunities": self._base / "opportunities.json",
            "scopes": self._base / "scopes.json",
            "complexity": self._base / "complexity.json",
            "cost": self._base / "cost.json",
            "capacity": self._base / "capacity.json",
            "pricing": self._base / "pricing.json",
            "operating_models": self._base / "operating-models.json",
            "commitments": self._base / "commitments.json",
            "approvals": self._base / "approvals.json",
            "journal": self._base / "journal.json",
            "sources": self._base / "ecrm-sources.json",
        }
        self._sealed_dir = self._base / "sealed"
        self._sealed_dir.mkdir(parents=True, exist_ok=True)
        if not (self._base / ".seeded").exists():
            self._seed()
            (self._base / ".seeded").write_text("ok", encoding="utf-8")

    # ────────────────── persistence ──────────────────

    def _read(self, key: str) -> list[dict]:
        with self._lock:
            data = _read_json(self._files[key])
            return data if isinstance(data, list) else []

    def _write(self, key: str, items: list[dict]) -> None:
        with self._lock:
            _atomic_write_json(self._files[key], items)

    def _upsert_by(self, key: str, items: list[dict], id_field: str, record: dict) -> None:
        idx = next((i for i, it in enumerate(items) if it.get(id_field) == record.get(id_field)), -1)
        if idx >= 0:
            items[idx] = record
        else:
            items.append(record)
        self._write(key, items)

    # ────────────────── UPM catalog (read-only) ──────────────────

    def upm_all(self) -> list[dict]:
        return [{"upm_code": c, **info} for c, info in sorted(UPM_CATALOG.items())]

    def upm_get(self, upm_code: str) -> Optional[dict]:
        info = UPM_CATALOG.get(upm_code)
        return None if info is None else {"upm_code": upm_code, **info}

    def app_registry_all(self) -> list[dict]:
        return [{"app_id": a, **info} for a, info in sorted(APP_REGISTRY.items())]

    # ────────────────── Opportunity ──────────────────

    def opp_upsert(self, opp: Opportunity) -> None:
        items = self._read("opportunities")
        opp.updated_at = now_iso()
        self._upsert_by("opportunities", items, "opportunity_id", asdict(opp))

    def opp_get(self, opp_id: OpportunityId) -> Optional[Opportunity]:
        for it in self._read("opportunities"):
            if it["opportunity_id"] == opp_id:
                return _opp_from_dict(it)
        return None

    def opp_list(self) -> list[Opportunity]:
        return [_opp_from_dict(it) for it in self._read("opportunities")]

    def opp_delete(self, opp_id: OpportunityId) -> bool:
        items = self._read("opportunities")
        new_items = [it for it in items if it["opportunity_id"] != opp_id]
        if len(new_items) == len(items):
            return False
        self._write("opportunities", new_items)
        return True

    # ────────────────── Scope (S02) ──────────────────

    def scope_compute(self, opp_id: OpportunityId) -> ScopeManifest:
        opp = self.opp_get(opp_id)
        if opp is None:
            raise KeyError(f"Opportunity not found: {opp_id}")
        line_items: list[ScopeLineItem] = []
        issues: list[ScopeIssue] = []
        all_apps: set[str] = set()
        requested = list(opp.scope_summary.products_requested)
        # Walk dependencies (closure)
        resolved: list[str] = []
        for code in requested:
            self._resolve_with_deps(code, resolved, requested_set=set(requested))
        legal_assignment: dict[str, str] = {}
        for code in resolved:
            info = UPM_CATALOG.get(code)
            if info is None:
                issues.append(ScopeIssue("blocking", "UPM_UNKNOWN", f"Unknown UPM code: {code}", code))
                continue
            if info["status"] != "active":
                issues.append(ScopeIssue("warn", "UPM_STATUS",
                                          f"UPM status is {info['status']}: {code}", code))
            for j in opp.scope_summary.jurisdictions:
                if j not in info["eligible_jurisdictions"]:
                    issues.append(ScopeIssue(
                        "blocking", "JURIS_INELIGIBLE",
                        f"{code} not eligible in {j}", code))
                else:
                    le = info["legal_entities"][0]
                    legal_assignment.setdefault(j, le)
                    line_items.append(ScopeLineItem(
                        upm_code=code,
                        label=info["label"],
                        jurisdiction=j,
                        legal_entity=le,
                        delivery_stack=[DeliveryStackEntry(**d) for d in info["delivery_stack"]],
                        dependencies=list(info["dependencies"]),
                    ))
                    for d in info["delivery_stack"]:
                        all_apps.add(d["app_id"])
        # Dependency-missing check (after resolution, original requested vs added)
        for code in resolved:
            info = UPM_CATALOG.get(code)
            if info is None:
                continue
            for dep in info["dependencies"]:
                if dep not in resolved:
                    issues.append(ScopeIssue(
                        "blocking", "DEP_MISSING",
                        f"{code} depends on {dep} which is not in scope", code))

        scope = ScopeManifest(
            scope_manifest_id=f"scope_{_ulid()}",
            opportunity_id=opp_id,
            upm_snapshot_version="upm_v2026.05.13",
            line_items=line_items,
            legal_entity_assignment=legal_assignment,
            derived_app_set=sorted(all_apps),
            derived_jurisdictions=sorted(opp.scope_summary.jurisdictions),
            issues=issues,
        )
        self._upsert_by("scopes", self._read("scopes"), "scope_manifest_id", asdict(scope))
        opp.scope_manifest_id = scope.scope_manifest_id
        opp.status = "scoping" if not scope.blocking else "scoping"
        self.opp_upsert(opp)
        self.journal_append(opp_id, "scope", {"scope_manifest_id": scope.scope_manifest_id,
                                              "issues_count": len(issues),
                                              "blocking": scope.blocking})
        return scope

    def _resolve_with_deps(self, code: str, out: list[str], requested_set: set[str]) -> None:
        if code in out:
            return
        info = UPM_CATALOG.get(code)
        if info is not None:
            for dep in info["dependencies"]:
                if dep not in requested_set:   # auto-add hard deps
                    self._resolve_with_deps(dep, out, requested_set | {dep})
        out.append(code)

    def scope_for(self, opp_id: OpportunityId) -> Optional[ScopeManifest]:
        for it in self._read("scopes"):
            if it["opportunity_id"] == opp_id:
                return _scope_from_dict(it)
        return None

    # ────────────────── Complexity (S04) ──────────────────

    def complexity_score(self, opp_id: OpportunityId) -> ComplexityScorecard:
        opp = self.opp_get(opp_id)
        if opp is None:
            raise KeyError(opp_id)
        scope = self.scope_for(opp_id)
        if scope is None:
            raise ValueError("Cannot score complexity before scope is computed")

        scores: dict[str, int] = {}
        # fund_count_structure: based on number of fund umbrella roles
        umbrellas = sum(1 for r in opp.client.entity_tree_roles if r.role in ("fund_umbrella", "sub_fund"))
        scores["fund_count_structure"] = min(5, max(1, 1 + umbrellas // 3))
        # jurisdictional_spread
        n_juris = len(scope.derived_jurisdictions)
        scores["jurisdictional_spread"] = (
            1 if n_juris <= 1 else 2 if n_juris <= 3 else 3 if n_juris <= 6 else 4 if n_juris <= 8 else 5
        )
        # asset_class_breadth: variety of UPM family prefixes
        families = {li.upm_code.split(".")[0] for li in scope.line_items}
        scores["asset_class_breadth"] = min(5, max(1, len(families) - 1))
        # nav_cadence_sla
        ns = opp.scope_summary.nav_strikes_per_day
        scores["nav_cadence_sla"] = (
            1 if ns <= 5 else 2 if ns <= 20 else 3 if ns <= 50 else 4 if ns <= 100 else 5
        )
        # regulatory_regime_coverage
        regimes = {li.upm_code for li in scope.line_items if "regulatory_reporting" in li.upm_code or "depo" in li.upm_code}
        scores["regulatory_regime_coverage"] = (
            1 if not regimes else min(5, 1 + len(regimes))
        )
        # bespoke_reporting: heuristic from estimated AUM tier
        aum = opp.scope_summary.estimated_aum_usd
        scores["bespoke_reporting"] = (
            1 if aum < 1e9 else 2 if aum < 10e9 else 3 if aum < 50e9 else 4 if aum < 200e9 else 5
        )
        # client_system_integration_footprint: from cross-sell / existing products
        existing = len(opp.relationship.existing_products)
        scores["client_system_integration_footprint"] = min(5, max(1, 1 + existing))
        # transition_aggression: heuristic from go-live distance
        scores["transition_aggression"] = 4 if opp.scope_summary.indicative_go_live and opp.scope_summary.indicative_go_live < "2027-01-01" else 2
        # servicing_model_dedicated_vs_pooled
        scores["servicing_model_dedicated_vs_pooled"] = 4 if aum >= 50e9 else 2
        # data_residency_constraints
        scores["data_residency_constraints"] = 4 if "DE" in scope.derived_jurisdictions or "CN" in scope.derived_jurisdictions else 2

        weights = {k: 0.10 for k in COMPLEXITY_DIMENSIONS}   # uniform v1
        composite = sum(weights[k] * scores[k] for k in COMPLEXITY_DIMENSIONS)
        if composite <= 2.0:
            tier: ApprovalTier = "tier_1_rm_segment_head"   # not used directly here
            tier_label = "T1_low"
        elif composite < 3.0:
            tier_label = "T2_standard"
        elif composite < 4.0:
            tier_label = "T3_high"
        else:
            tier_label = "T4_exceptional"

        dim_scores = [
            ComplexityDimensionScore(key=k, score=scores[k], notes=_complexity_note(k, scores[k]))
            for k in COMPLEXITY_DIMENSIONS
        ]
        card = ComplexityScorecard(
            complexity_id=f"cx_{_ulid()}",
            opportunity_id=opp_id,
            scorecard_version="cx_v1.0",
            dimensions=dim_scores,
            weights=weights,
            composite_score=round(composite, 2),
            tier=tier_label,   # type: ignore[arg-type]
            rationale_narrative=(
                f"Composite {composite:.2f} → {tier_label}. "
                f"Drivers: jurisdiction {scores['jurisdictional_spread']}, "
                f"NAV cadence {scores['nav_cadence_sla']}, "
                f"asset breadth {scores['asset_class_breadth']}."
            ),
        )
        self._upsert_by("complexity", self._read("complexity"), "complexity_id", asdict(card))
        opp.complexity_id = card.complexity_id
        opp.status = "complexity"
        self.opp_upsert(opp)
        self.journal_append(opp_id, "complexity.score",
                            {"complexity_id": card.complexity_id,
                             "composite": card.composite_score,
                             "tier": card.tier})
        return card

    def complexity_for(self, opp_id: OpportunityId) -> Optional[ComplexityScorecard]:
        for it in self._read("complexity"):
            if it["opportunity_id"] == opp_id:
                return _complexity_from_dict(it)
        return None

    # ────────────────── Cost engine (S05a) ──────────────────

    def cost_compute(self, opp_id: OpportunityId) -> CostStack:
        opp = self.opp_get(opp_id)
        scope = self.scope_for(opp_id)
        complexity = self.complexity_for(opp_id)
        if opp is None or scope is None or complexity is None:
            raise ValueError("scope + complexity required before cost")

        # Volume-driven FTE estimates per UPM family
        fte: list[FteLine] = []
        navs = opp.scope_summary.nav_strikes_per_day
        cx_factor = 0.85 + 0.1 * (complexity.composite_score - 2.0)   # 0.85 .. 1.35
        # Fund accounting FTE per function/location, scaled
        if any("fa." in li.upm_code for li in scope.line_items):
            prim_loc = "lux" if "LU" in scope.derived_jurisdictions else "dublin"
            fa_count = max(4.0, round(navs * cx_factor / 6.0, 1))
            fte.append(FteLine("fund_accounting", prim_loc, "fa_specialist_l2",
                               fa_count, ROLE_RATES[("fa_specialist_l2", prim_loc)], 1))
            fte.append(FteLine("fund_accounting", "pune", "fa_specialist_l2",
                               max(2.0, round(fa_count * 0.6, 1)),
                               ROLE_RATES[("fa_specialist_l2", "pune")], 1))
        if any(li.upm_code == "custody.global" for li in scope.line_items):
            fte.append(FteLine("custody_corp_actions", "pune", "ca_specialist_l1",
                               max(3.0, round(opp.scope_summary.transactions_per_year / 80_000, 1)),
                               ROLE_RATES[("ca_specialist_l1", "pune")], 1))
        if any(li.upm_code.startswith("ta.") for li in scope.line_items):
            ta_loc = "lux" if any(li.upm_code == "ta.lux" for li in scope.line_items) else "dublin"
            fte.append(FteLine("transfer_agency", ta_loc, "ta_specialist",
                               max(2.0, round(opp.scope_summary.shareholders / 50_000, 1)),
                               ROLE_RATES[("ta_specialist", ta_loc)], 1))
        if any(li.upm_code.startswith("alts.") for li in scope.line_items):
            fte.append(FteLine("alts_admin", "ny", "alts_admin_specialist",
                               max(2.0, round(opp.scope_summary.capital_events_per_year / 300, 1)),
                               ROLE_RATES[("alts_admin_specialist", "ny")], 1))
        if any(li.upm_code.startswith("depo.") for li in scope.line_items):
            depo_loc = "lux" if "LU" in scope.derived_jurisdictions else "dublin"
            fte.append(FteLine("depositary", depo_loc, "depo_controller",
                               max(2.0, round(navs / 30.0, 1)),
                               ROLE_RATES[("depo_controller", depo_loc)], 1))
        # Client service layer for tiered deals
        cs_count = 2.0 if complexity.composite_score < 3.0 else 4.0
        fte.append(FteLine("client_service", "ny", "client_service_director",
                           1.0, ROLE_RATES[("client_service_director", "ny")], 1))
        fte.append(FteLine("client_service", "lux", "client_service_manager",
                           cs_count, ROLE_RATES[("client_service_manager", "lux")], 1))
        # Reg reporting
        if any(li.upm_code.startswith("fadmin.regulatory_reporting") for li in scope.line_items):
            rr_loc = "dublin" if "IE" in scope.derived_jurisdictions else "lux"
            fte.append(FteLine("regulatory_reporting", rr_loc, "regulatory_reporter",
                               max(1.0, round(navs / 50.0, 1)),
                               ROLE_RATES[("regulatory_reporter", rr_loc)], 1))

        # Sub-custody passthrough for jurisdictions outside dom set
        sub_custody = [
            SubCustodyLine(j, SUB_CUSTODY_RATES.get(j, 35_000))
            for j in scope.derived_jurisdictions
            if j in SUB_CUSTODY_RATES and j not in ("IE", "LU")
        ]
        # Technology run cost (per app)
        tech_run: list[TechRunCostLine] = []
        tech_exp: list[TechExpansionLine] = []
        cap = self.capacity_compute(opp_id, persist=False)   # consult capacity to derive expansion
        for app in scope.derived_app_set:
            tech_run.append(TechRunCostLine(app, 120_000 + len(scope.line_items) * 18_000, "per_app_per_year"))
        for impact in cap.app_impacts:
            if impact.verdict == "expansion_required":
                tech_exp.append(TechExpansionLine(impact.app_id, impact.expansion_cost_usd, True, impact.lead_time_weeks))

        # Transition one-time
        impl_fte = int(sum(f.fully_loaded_rate_usd * f.count for f in fte) * 0.18)
        transition = TransitionOneTime(
            implementation_fte_usd=impl_fte,
            parallel_running_usd=int(impl_fte * 0.22),
            data_migration_usd=180_000 + 25_000 * len(scope.derived_jurisdictions),
            client_integration_build_usd=240_000 + 50_000 * (1 if complexity.composite_score >= 3.0 else 0),
        )
        # Risk / compliance
        risk = [
            RiskComplianceLine("aml_monitoring", 95_000),
            RiskComplianceLine("trade_surveillance", 60_000),
        ]

        # Year totals
        def _year_total(year: int) -> int:
            fte_year = sum(int(f.fully_loaded_rate_usd * f.count) for f in fte) * (1 + 0.03 * (year - 1))
            run_year = sum(t.annual_usd for t in tech_run) * (1 + 0.02 * (year - 1))
            risk_year = sum(r.annual_usd for r in risk)
            sub_year = sum(s.annual_usd for s in sub_custody) * 0.2   # 80% pass-through; 20% retained
            return int(fte_year + run_year + risk_year + sub_year)

        y1 = _year_total(1) + sum(t.expansion_cost_usd for t in tech_exp) + (
            transition.implementation_fte_usd + transition.parallel_running_usd
            + transition.data_migration_usd + transition.client_integration_build_usd
        )
        y2 = _year_total(2)
        y3 = _year_total(3)
        # NPV @ 8% over 5 years (linear approx for determinism)
        npv = int(y1 / 1.08 + y2 / 1.08 ** 2 + y3 / 1.08 ** 3
                  + _year_total(4) / 1.08 ** 4 + _year_total(5) / 1.08 ** 5)

        stack = CostStack(
            cost_stack_id=f"cost_{_ulid()}",
            opportunity_id=opp_id,
            horizon_years=5,
            direct_fte=fte,
            sub_custody_passthrough=sub_custody,
            technology_run_cost=tech_run,
            technology_capacity_expansion=tech_exp,
            transition_one_time=transition,
            risk_compliance_overhead=risk,
            allocated_overhead_pct=0.18,
            totals=CostTotals(y1, y2, y3, npv),
        )
        self._upsert_by("cost", self._read("cost"), "cost_stack_id", asdict(stack))
        opp.cost_stack_id = stack.cost_stack_id
        opp.status = "cost_capacity"
        self.opp_upsert(opp)
        self.journal_append(opp_id, "cost.compute",
                            {"cost_stack_id": stack.cost_stack_id,
                             "year_1_total_usd": stack.totals.year_1_total_usd,
                             "five_year_npv_usd": stack.totals.five_year_npv_usd})
        return stack

    def cost_for(self, opp_id: OpportunityId) -> Optional[CostStack]:
        for it in self._read("cost"):
            if it["opportunity_id"] == opp_id:
                return _cost_from_dict(it)
        return None

    # ────────────────── Capacity engine (S05b) ──────────────────

    def capacity_compute(self, opp_id: OpportunityId, persist: bool = True) -> CapacityImpact:
        opp = self.opp_get(opp_id)
        scope = self.scope_for(opp_id)
        if opp is None or scope is None:
            raise ValueError("scope required before capacity")

        impacts: list[AppImpact] = []
        blocks: list[BlockingConstraint] = []
        for app_id in scope.derived_app_set:
            app = APP_REGISTRY.get(app_id)
            if app is None:
                continue
            # Compute delta per metric based on load_factor
            projected_delta: dict[str, float] = {}
            for li in scope.line_items:
                for ds in li.delivery_stack:
                    if ds.app_id != app_id:
                        continue
                    units = _units_for_load_factor(ds.load_factor, opp.scope_summary)
                    factors = app["load_per_unit"].get(ds.load_factor, {})
                    for metric, mult in factors.items():
                        projected_delta[metric] = projected_delta.get(metric, 0.0) + units * mult
            # Post-deal utilization
            post: dict[str, float] = {}
            verdict: str = "fits_in_headroom"
            for metric, delta in projected_delta.items():
                cap_val = app["capacity"].get(metric)
                cur_val = app["capacity"].get(f"{metric}_current") or app["capacity"].get("current")
                if cap_val is None or cur_val is None:
                    continue
                post_val = (cur_val + delta) / cap_val * 100.0
                post[metric] = round(post_val, 2)
                if post_val >= 95.0:
                    verdict = "expansion_required"
                    blocks.append(BlockingConstraint(
                        app_id, f"{metric} projected at {post_val:.1f}% post-deal", "high"))
                elif post_val >= 85.0 and verdict == "fits_in_headroom":
                    verdict = "declining_risk"
            impacts.append(AppImpact(
                app_id=app_id,
                label=app["label"],
                projected_delta={k: round(v, 2) for k, v in projected_delta.items()},
                post_deal_utilization_pct=post,
                verdict=verdict,   # type: ignore[arg-type]
                recommended_action=app["expansion"]["step"],
                expansion_cost_usd=app["expansion"]["cost_usd"] if verdict == "expansion_required" else 0,
                lead_time_weeks=app["expansion"]["lead_time_weeks"] if verdict == "expansion_required" else 0,
            ))

        impact = CapacityImpact(
            capacity_impact_id=f"cap_{_ulid()}",
            opportunity_id=opp_id,
            app_impacts=impacts,
            blocking_constraints=blocks,
        )
        if persist:
            self._upsert_by("capacity", self._read("capacity"), "capacity_impact_id", asdict(impact))
            opp.capacity_id = impact.capacity_impact_id
            self.opp_upsert(opp)
            self.journal_append(opp_id, "capacity.analyze",
                                {"capacity_impact_id": impact.capacity_impact_id,
                                 "blocking_count": len(blocks)})
        return impact

    def capacity_for(self, opp_id: OpportunityId) -> Optional[CapacityImpact]:
        for it in self._read("capacity"):
            if it["opportunity_id"] == opp_id:
                return _capacity_from_dict(it)
        return None

    # ────────────────── Pricing engine (S06) ──────────────────

    def pricing_propose(self, opp_id: OpportunityId) -> PricingProposal:
        opp = self.opp_get(opp_id)
        cost = self.cost_for(opp_id)
        complexity = self.complexity_for(opp_id)
        if opp is None or cost is None or complexity is None:
            raise ValueError("cost + complexity required before pricing")

        aum = max(1, opp.scope_summary.estimated_aum_usd)
        # Asset-based fee bands — bp drops as AUM grows
        asset_based = [
            AssetBasedTier(
                asset_class="developed_eq",
                tiers=[
                    AssetBandFee(0, 5_000_000_000, 1.6),
                    AssetBandFee(5_000_000_000, 20_000_000_000, 1.1),
                    AssetBandFee(20_000_000_000, 1_000_000_000_000, 0.7),
                ],
            ),
        ]
        if any(li.upm_code.startswith("alts.") for li in self.scope_for(opp_id).line_items):
            asset_based.append(AssetBasedTier(
                asset_class="alts_pe",
                tiers=[AssetBandFee(0, 2_000_000_000, 9.0),
                       AssetBandFee(2_000_000_000, 1_000_000_000_000, 6.5)],
            ))
        transactional = [
            {"event": "trade_settlement", "fee_usd": 4.50},
            {"event": "corp_action", "fee_usd": 18.00},
            {"event": "nav_strike", "fee_usd": 85.00},
        ]
        fixed = [FixedRetainer("board_reporting", 240_000)]

        fee_structure = FeeStructure(
            asset_based=asset_based,
            transactional=[],   # populated below with proper TransactionalFee dataclasses
            fixed_retainers=fixed,
            passthrough_oop=["sub_custody", "swift", "regulatory_fees"],
            minimum_fee_floor_usd_annual=max(2_000_000, int(cost.totals.year_1_total_usd * 0.9 / 5)),
            term_years=5,
            term_discount_pct=0.08,
            bundled_discount_pct=0.05 if len(opp.scope_summary.products_requested) >= 3 else 0.0,
        )
        # Rebuild transactional with proper dataclass
        from core.domain.opp_deal import TransactionalFee
        fee_structure.transactional = [TransactionalFee(**t) for t in transactional]

        # Direct fee (year 1): bp on AUM via tier walk
        def _bp_revenue(class_aum: int, tiers: list[AssetBandFee]) -> int:
            rem = class_aum
            total = 0.0
            for t in tiers:
                band = max(0, min(rem, t.aum_band_usd_max - t.aum_band_usd_min))
                total += band * (t.bp / 10_000.0)
                rem -= band
                if rem <= 0:
                    break
            return int(total)

        direct_fee_y1 = _bp_revenue(aum, asset_based[0].tiers)
        if len(asset_based) > 1:
            direct_fee_y1 += _bp_revenue(int(aum * 0.05), asset_based[1].tiers)
        direct_fee_y1 += sum(f.annual_usd for f in fixed)
        direct_fee_y1 = max(direct_fee_y1, fee_structure.minimum_fee_floor_usd_annual)

        sec_lend_y1 = int(aum * 0.0008 * 0.25)
        fx_y1 = int(aum * 0.00025)
        nii_y1 = int(aum * 0.00012)
        adj_y1 = int(aum * 0.00008)

        tcv_years: list[TotalClientValueYear] = []
        five_year_total = 0
        for y in range(1, 6):
            growth = 1 + 0.03 * (y - 1)
            tcv_years.append(TotalClientValueYear(
                year=y,
                direct_fee_usd=int(direct_fee_y1 * growth),
                sec_lending_revenue_usd=int(sec_lend_y1 * growth),
                fx_revenue_usd=int(fx_y1 * growth),
                nii_on_balances_usd=int(nii_y1 * growth),
                adjacent_revenue_usd=int(adj_y1 * growth),
            ))
            five_year_total += sum([tcv_years[-1].direct_fee_usd, tcv_years[-1].sec_lending_revenue_usd,
                                    tcv_years[-1].fx_revenue_usd, tcv_years[-1].nii_on_balances_usd,
                                    tcv_years[-1].adjacent_revenue_usd])

        # Margin
        margin_y1_direct = max(0.0, round((direct_fee_y1 - cost.totals.year_1_total_usd) / max(direct_fee_y1, 1), 3))
        margin_y1_total = max(0.0, round((sum([tcv_years[0].direct_fee_usd, tcv_years[0].sec_lending_revenue_usd,
                                               tcv_years[0].fx_revenue_usd, tcv_years[0].nii_on_balances_usd,
                                               tcv_years[0].adjacent_revenue_usd])
                                          - cost.totals.year_1_total_usd) / max(direct_fee_y1, 1), 3))
        npv5 = five_year_total - cost.totals.five_year_npv_usd
        irr = round(0.10 + 0.02 * complexity.composite_score, 3) if cost.totals.five_year_npv_usd else 0.0
        payback = round(cost.totals.year_1_total_usd / max(direct_fee_y1, 1), 1)
        margin = MarginAnalysis(
            year_1_direct_margin_pct=margin_y1_direct,
            year_1_total_margin_pct=margin_y1_total,
            five_year_npv_usd=npv5,
            irr_pct=irr,
            payback_years=payback,
        )

        # Sensitivities
        sens = [
            SensitivityScenario("aum_minus_20pct", round(-0.04, 3), int(npv5 * 0.78)),
            SensitivityScenario("fx_revenue_minus_50pct", round(-0.02, 3), int(npv5 * 0.91)),
            SensitivityScenario("transition_overrun_20pct", round(-0.025, 3), int(npv5 * 0.86)),
            SensitivityScenario("rate_curve_flat", round(-0.015, 3), int(npv5 * 0.93)),
            SensitivityScenario("competitive_bp_minus_10pct", round(-0.025, 3), int(npv5 * 0.88)),
        ]

        # Approval tier
        tier = self._approval_tier(complexity.tier, npv5)
        proposal = PricingProposal(
            pricing_proposal_id=f"px_{_ulid()}",
            opportunity_id=opp_id,
            fee_structure=fee_structure,
            sec_lending=SecLendingShare(75, 25),
            fx_revenue=FxRevenueModel(2.5, "transparent"),
            total_client_value=TotalClientValue(by_year=tcv_years, five_year_total_usd=five_year_total),
            margin_analysis=margin,
            sensitivity=sens,
            approval_tier_required=tier,
            rationale_narrative=(
                f"Year-1 direct fee USD{direct_fee_y1:,}; "
                f"Year-1 total margin {margin.year_1_total_margin_pct:.1%}; "
                f"5-yr NPV USD{npv5:,}; tier {tier}."
            ),
        )
        self._upsert_by("pricing", self._read("pricing"), "pricing_proposal_id", asdict(proposal))
        opp.pricing_id = proposal.pricing_proposal_id
        opp.status = "pricing"
        self.opp_upsert(opp)
        self.journal_append(opp_id, "pricing.propose",
                            {"pricing_proposal_id": proposal.pricing_proposal_id,
                             "five_year_npv_usd": npv5,
                             "approval_tier_required": tier})
        return proposal

    def _approval_tier(self, complexity_tier: str, npv_usd: int) -> ApprovalTier:
        # Tier table from spec §S08
        if complexity_tier == "T4_exceptional" or npv_usd >= 100_000_000:
            return "tier_4_segment_ceo_cfo"
        if complexity_tier == "T3_high" or npv_usd >= 25_000_000:
            return "tier_3_cfo_coo_risk"
        if npv_usd >= 5_000_000:
            return "tier_2_segment_head_cfo_delegate"
        return "tier_1_rm_segment_head"

    def pricing_for(self, opp_id: OpportunityId) -> Optional[PricingProposal]:
        for it in self._read("pricing"):
            if it["opportunity_id"] == opp_id:
                return _pricing_from_dict(it)
        return None

    # ────────────────── DDQ commitments (S03) ──────────────────

    def commitments_set(self, opp_id: OpportunityId, commitments: list[Commitment]) -> CommitmentSet:
        ddq_run_id = commitments[0].ddq_run_id if commitments else f"run_{_ulid()}"
        cs = CommitmentSet(opp_id, ddq_run_id, commitments)
        # Store as single dict (one set per opportunity)
        items = self._read("commitments")
        record = {
            "opportunity_id": opp_id,
            "ddq_run_id": ddq_run_id,
            "commitments": [asdict(c) for c in commitments],
        }
        self._upsert_by("commitments", items, "opportunity_id", record)
        opp = self.opp_get(opp_id)
        if opp is not None:
            opp.ddq_run_id = ddq_run_id
            self.opp_upsert(opp)
        self.journal_append(opp_id, "ddq.link", {"ddq_run_id": ddq_run_id,
                                                 "commitment_count": len(commitments)})
        for c in commitments:
            self.journal_append(opp_id, "ddq.commitment", {
                "commitment_id": c.commitment_id,
                "canonical_id": c.canonical_id,
                "class": c.commitment_class,
                "material": c.material,
            })
        return cs

    def commitments_for(self, opp_id: OpportunityId) -> Optional[CommitmentSet]:
        for it in self._read("commitments"):
            if it["opportunity_id"] == opp_id:
                return CommitmentSet(
                    opportunity_id=opp_id,
                    ddq_run_id=it["ddq_run_id"],
                    commitments=[_commitment_from_dict(c) for c in it["commitments"]],
                )
        return None

    # ────────────────── Operating model (S07) ──────────────────

    def operating_model_design(self, opp_id: OpportunityId) -> OperatingModelPlan:
        opp = self.opp_get(opp_id)
        scope = self.scope_for(opp_id)
        cost = self.cost_for(opp_id)
        cap = self.capacity_for(opp_id)
        if opp is None or scope is None or cost is None or cap is None:
            raise ValueError("scope, cost, capacity required before operating model")
        commitments = self.commitments_for(opp_id) or CommitmentSet(opp_id, "run_none", [])

        primary_op_loc = "lux" if "LU" in scope.derived_jurisdictions else "dublin"
        client_layer = ServiceModelLayer(
            model="dedicated" if (self.complexity_for(opp_id) and self.complexity_for(opp_id).composite_score >= 3.0) else "hybrid",
            named_roles=[
                NamedRole("client_service_director", "ny", "tbd"),
                NamedRole("head_of_client_service", primary_op_loc, "tbd"),
            ],
            governance_cadence=[
                GovernanceForum("operating_committee", "weekly", ["client_service_director", "head_of_ops"]),
                GovernanceForum("steering_committee", "monthly", ["exec_sponsor", "client_service_director", "rm"]),
                GovernanceForum("exec_sponsor_review", "quarterly", ["exec_sponsor", "client_cfo"]),
            ],
            escalation_path=["client_service_director", "segment_head", "as_coo"],
        )
        ops_footprint = [
            FunctionalFootprint(function="fund_accounting", primary_location=primary_op_loc, follow_the_sun=["pune"]),
            FunctionalFootprint(function="custody_corp_actions", primary_location="pune", follow_the_sun=["ny"]),
            FunctionalFootprint(function="client_service", primary_location="ny", follow_the_sun=[primary_op_loc]),
        ]

        # FTE plan reconciled against CostStack.direct_fte
        hires: list[HireRequisition] = []
        today = "2026-05-13"
        for fl in cost.direct_fte:
            weeks = LOCATION_HIRING_WEEKS.get(fl.location, 14)
            transition_risk = "high" if opp.scope_summary.indicative_go_live and opp.scope_summary.indicative_go_live < "2027-04-01" and weeks >= 16 else "medium" if weeks >= 14 else "low"
            hires.append(HireRequisition(
                role=fl.role,
                location=fl.location,
                count=fl.count,
                hiring_start="2026-06-01",
                hiring_lead_time_weeks=weeks,
                transition_risk=transition_risk,
            ))
        total_fte_y1 = sum(fl.count for fl in cost.direct_fte)
        fte_plan = FtePlan(
            by_year=[FteYearPlan(year=1, net_new_hires=hires, redeployment_count=2.0, total_fte=total_fte_y1)],
            parallel_running_weeks=12,
            parallel_running_fte_overhead=round(total_fte_y1 * 0.2, 1),
            transition_milestones=[
                TransitionMilestone("first_nav_parallel", "2026-11-15", ["hiring.tranche_1"]),
                TransitionMilestone("cutover", opp.scope_summary.indicative_go_live or "2027-01-01"),
            ],
        )

        app_impact = [
            AppImpactSummary(
                app_id=ai.app_id,
                scope_role="primary" if ai.verdict == "expansion_required" else "supporting",
                capacity_action=ai.recommended_action,
                go_live_dependency=ai.verdict == "expansion_required",
            )
            for ai in cap.app_impacts
        ]
        integration_builds = [
            IntegrationBuild("client_oms_aladdin_fix", 8, "client_connectivity_team"),
            IntegrationBuild("custodian_swift_mt54x", 4, "client_connectivity_team"),
        ]
        reporting_builds = [
            ReportingBuild("bespoke_solvency_ii_extract", 6, "reporting_team") if "DE" in scope.derived_jurisdictions else ReportingBuild("standard_factsheet_pack", 3, "reporting_team"),
        ]

        # Resilience: pull RTO from DDQ commitments if any are SLA commitments
        rto_commits: list[RtoRpoCommitment] = []
        for c in commitments.commitments:
            if c.commitment_class == "sla" and "rto" in c.commitment_text.lower():
                rto_commits.append(RtoRpoCommitment(
                    service="fund_accounting", rto_hours=4, rpo_minutes=15, ddq_commitment_ref=c.commitment_id,
                ))
        if not rto_commits:
            rto_commits.append(RtoRpoCommitment("fund_accounting", 4, 15, None))
        resilience = ResiliencePosture(
            bcp_coverage_per_location=[primary_op_loc, "pune"],
            single_points_of_failure_added=[],
            rto_rpo_commitments=rto_commits,
        )

        controls = ControlEnvironmentChanges(
            new_controls=["client_data_segregation_v2"],
            extended_controls=["sox_404_fa", "iss_aml_oversight"],
            soc_scope_change_required=True,
            soc_scope_change_cost_usd=85_000,
            audit_readiness_milestone="2026-12-15",
        )

        # Commitment cross-check: SLA commitments map to resilience; control commitments to controls
        crosscheck: list[CommitmentCrosscheck] = []
        for c in commitments.commitments:
            if not c.material:
                continue
            met_by = None
            status: str = "unmet"
            if c.commitment_class == "sla":
                met_by = "resilience_posture.rto_rpo_commitments[0]"
                status = "met"
            elif c.commitment_class in ("control", "reporting"):
                met_by = "control_environment.new_controls" if "control_environment" else None
                status = "met"
            elif c.commitment_class == "data_residency":
                met_by = "operational_footprint"
                status = "met" if c.commitment_text.lower().find("eu") < 0 or primary_op_loc in ("lux", "dublin") else "unmet"
            else:
                met_by = "control_environment.new_controls"
                status = "met"
            crosscheck.append(CommitmentCrosscheck(c.commitment_id, met_by, status))   # type: ignore[arg-type]

        plan = OperatingModelPlan(
            operating_model_id=f"om_{_ulid()}",
            opportunity_id=opp_id,
            client_service_layer=client_layer,
            operational_footprint=ops_footprint,
            fte_plan=fte_plan,
            app_impact=app_impact,
            integration_builds=integration_builds,
            reporting_builds=reporting_builds,
            resilience_posture=resilience,
            control_environment=controls,
            ddq_commitment_crosscheck=crosscheck,
        )
        self._upsert_by("operating_models", self._read("operating_models"), "operating_model_id", asdict(plan))
        opp.operating_model_id = plan.operating_model_id
        opp.status = "operating_model"
        self.opp_upsert(opp)
        self.journal_append(opp_id, "operating_model.design",
                            {"operating_model_id": plan.operating_model_id,
                             "unmet_count": sum(1 for c in crosscheck if c.status == "unmet")})
        return plan

    def operating_model_for(self, opp_id: OpportunityId) -> Optional[OperatingModelPlan]:
        for it in self._read("operating_models"):
            if it["opportunity_id"] == opp_id:
                return _opmodel_from_dict(it)
        return None

    # ────────────────── Approval + seal (S08) ──────────────────

    def approval_request(self, opp_id: OpportunityId) -> ApprovalRequest:
        pricing = self.pricing_for(opp_id)
        opm = self.operating_model_for(opp_id)
        if pricing is None or opm is None:
            raise ValueError("pricing + operating model required before approval")
        if opm.has_unmet_commitments:
            raise ValueError("operating model has unmet commitments — cannot request approval (guardrail.03)")
        cap = self.capacity_for(opp_id)
        if cap and any(b.severity == "high" for b in cap.blocking_constraints):
            raise ValueError("capacity has unresolved high-severity blockers — cannot request approval (guardrail.04)")

        tier = pricing.approval_tier_required
        approvers_required = _approvers_for_tier(tier)
        req = ApprovalRequest(
            request_id=f"appr_{_ulid()}",
            opportunity_id=opp_id,
            tier_required=tier,
            approvers_required=approvers_required,
        )
        self._upsert_by("approvals", self._read("approvals"), "opportunity_id",
                        {**asdict(req), "opportunity_id": opp_id})
        opp = self.opp_get(opp_id)
        if opp:
            opp.status = "approval"
            self.opp_upsert(opp)
        self.journal_append(opp_id, "approval.request",
                            {"request_id": req.request_id, "tier": tier,
                             "approvers_required": approvers_required})
        return req

    def approval_decide(self, opp_id: OpportunityId, role: str,
                        user_id: str, comment: str = "") -> ApprovalRequest:
        items = self._read("approvals")
        record = next((it for it in items if it.get("opportunity_id") == opp_id), None)
        if record is None:
            raise KeyError(f"no approval request for {opp_id}")
        # decisions list
        decisions = record.get("decisions", [])
        decisions.append({
            "role": role,
            "user_id": user_id,
            "ts": now_iso(),
            "signature": "sig_" + hashlib.sha256(f"{role}|{user_id}|{opp_id}".encode()).hexdigest()[:16],
            "comment": comment,
        })
        record["decisions"] = decisions
        required = set(record["approvers_required"])
        present = {d["role"] for d in decisions}
        if required.issubset(present):
            record["state"] = "approved"
        else:
            record["state"] = "open"
        self._upsert_by("approvals", items, "opportunity_id", record)
        self.journal_append(opp_id, "approval.decision",
                            {"role": role, "user_id": user_id, "state": record["state"]})
        return _approval_from_dict(record)

    def approval_for(self, opp_id: OpportunityId) -> Optional[ApprovalRequest]:
        for it in self._read("approvals"):
            if it.get("opportunity_id") == opp_id:
                return _approval_from_dict(it)
        return None

    def seal(self, opp_id: OpportunityId) -> SealedDealBundle:
        appr = self.approval_for(opp_id)
        if appr is None or appr.state != "approved":
            raise ValueError("approval not complete — cannot seal (guardrail.05)")

        opp = self.opp_get(opp_id)
        scope = self.scope_for(opp_id)
        cx = self.complexity_for(opp_id)
        cost = self.cost_for(opp_id)
        cap = self.capacity_for(opp_id)
        px = self.pricing_for(opp_id)
        opm = self.operating_model_for(opp_id)
        commits = self.commitments_for(opp_id) or CommitmentSet(opp_id, "run_none", [])
        if not all([opp, scope, cx, cost, cap, px, opm]):
            raise ValueError("missing stage artifacts — cannot seal")

        scope_h = payload_hash(asdict(scope))
        cx_h = payload_hash(asdict(cx))
        cost_h = payload_hash(asdict(cost))
        cap_h = payload_hash(asdict(cap))
        px_h = payload_hash(asdict(px))
        opm_h = payload_hash(asdict(opm))
        cs_h = payload_hash(asdict(commits))

        bundle = SealedDealBundle(
            deal_id=f"deal_{_ulid()}",
            opportunity_id=opp_id,
            sealed_at=now_iso(),
            ucm_snapshot_version=opp.client.ucm_snapshot_version,
            upm_snapshot_version=scope.upm_snapshot_version,
            ddq_run_ids=[commits.ddq_run_id] if commits.ddq_run_id != "run_none" else [],
            scope_manifest_hash=scope_h,
            complexity_scorecard_hash=cx_h,
            cost_stack_hash=cost_h,
            capacity_impact_hash=cap_h,
            pricing_proposal_hash=px_h,
            operating_model_plan_hash=opm_h,
            commitment_set_hash=cs_h,
            approval_chain=list(appr.decisions),
            merkle_root=merkle_root([scope_h, cx_h, cost_h, cap_h, px_h, opm_h, cs_h]),
            platform_version=_PLATFORM_VERSION,
            handoff_targets=["contracting", "implementation_pm", "capacity_planning", "hr_recruitment", "ecrm"],
        )
        _atomic_write_json(self._sealed_dir / f"{bundle.deal_id}.json", asdict(bundle))
        opp.deal_id = bundle.deal_id
        opp.status = "won"
        self.opp_upsert(opp)
        self.journal_append(opp_id, "seal", {"deal_id": bundle.deal_id,
                                             "merkle_root": bundle.merkle_root})
        for target in bundle.handoff_targets:
            self.journal_append(opp_id, "handoff",
                                {"deal_id": bundle.deal_id, "target": target})
        return bundle

    def sealed_get(self, opp_id: OpportunityId) -> Optional[SealedDealBundle]:
        for path in sorted(self._sealed_dir.glob("*.json")):
            data = _read_json(path)
            if data and data.get("opportunity_id") == opp_id:
                return _bundle_from_dict(data)
        return None

    def replay(self, opp_id: OpportunityId) -> dict:
        bundle = self.sealed_get(opp_id)
        if bundle is None:
            return {"ok": False, "reason": "no sealed bundle"}
        scope = self.scope_for(opp_id)
        cx = self.complexity_for(opp_id)
        cost = self.cost_for(opp_id)
        cap = self.capacity_for(opp_id)
        px = self.pricing_for(opp_id)
        opm = self.operating_model_for(opp_id)
        commits = self.commitments_for(opp_id) or CommitmentSet(opp_id, "run_none", [])
        checks = {
            "scope_manifest_hash": bundle.scope_manifest_hash == payload_hash(asdict(scope)),
            "complexity_scorecard_hash": bundle.complexity_scorecard_hash == payload_hash(asdict(cx)),
            "cost_stack_hash": bundle.cost_stack_hash == payload_hash(asdict(cost)),
            "capacity_impact_hash": bundle.capacity_impact_hash == payload_hash(asdict(cap)),
            "pricing_proposal_hash": bundle.pricing_proposal_hash == payload_hash(asdict(px)),
            "operating_model_plan_hash": bundle.operating_model_plan_hash == payload_hash(asdict(opm)),
            "commitment_set_hash": bundle.commitment_set_hash == payload_hash(asdict(commits)),
        }
        expected_root = merkle_root([
            bundle.scope_manifest_hash, bundle.complexity_scorecard_hash,
            bundle.cost_stack_hash, bundle.capacity_impact_hash,
            bundle.pricing_proposal_hash, bundle.operating_model_plan_hash,
            bundle.commitment_set_hash,
        ])
        checks["merkle_root"] = expected_root == bundle.merkle_root
        return {"ok": all(checks.values()), "deal_id": bundle.deal_id,
                "checks": checks, "merkle_root": bundle.merkle_root}

    # ────────────────── Deal journal ──────────────────

    def journal_append(self, opp_id: OpportunityId, kind: str, payload: dict,
                       actor_id: str = "system", actor_role: str = "engine",
                       actor_kind: str = "system") -> DealJournalEvent:
        events = self._read("journal")
        prev_hash = "sha256:" + "0" * 64
        for e in reversed(events):
            if e.get("opportunity_id") == opp_id:
                prev_hash = e["chain_hash"]
                break
        ph = payload_hash(payload)
        event_id = f"evt_{_ulid()}"
        chain_hash = "sha256:" + hashlib.sha256(
            (prev_hash + event_id + ph).encode("utf-8")
        ).hexdigest()
        event = DealJournalEvent(
            event_id=event_id,
            opportunity_id=opp_id,
            deal_id=None,
            actor_kind=actor_kind,   # type: ignore[arg-type]
            actor_id=actor_id,
            actor_role=actor_role,
            kind=kind,   # type: ignore[arg-type]
            ts=now_iso(),
            payload=payload,
            payload_hash=ph,
            prev_hash=prev_hash,
            chain_hash=chain_hash,
        )
        events.append(asdict(event))
        self._write("journal", events)
        return event

    def journal_for(self, opp_id: OpportunityId) -> list[DealJournalEvent]:
        return [
            DealJournalEvent(**{k: v for k, v in e.items() if k in DealJournalEvent.__dataclass_fields__})
            for e in self._read("journal")
            if e.get("opportunity_id") == opp_id
        ]

    # ────────────────── eCRM source inbox (S01 pre-intake) ──────────────────

    def sources_list(self, state: Optional[str] = None) -> list[EcrmSource]:
        items = self._read("sources")
        if state is not None:
            items = [it for it in items if it.get("state") == state]
        return [_source_from_dict(it) for it in items]

    def source_get(self, source_id: str) -> Optional[EcrmSource]:
        for it in self._read("sources"):
            if it.get("source_id") == source_id:
                return _source_from_dict(it)
        return None

    def source_upsert(self, source: EcrmSource) -> None:
        items = self._read("sources")
        self._upsert_by("sources", items, "source_id", asdict(source))

    def source_promote(self, source_id: str) -> Opportunity:
        source = self.source_get(source_id)
        if source is None:
            raise KeyError(f"Source not found: {source_id}")
        if source.state == "promoted" and source.promoted_opportunity_id:
            existing = self.opp_get(source.promoted_opportunity_id)
            if existing is not None:
                return existing
        opp_id = f"opp_{_ulid()}"
        opp = Opportunity(
            opportunity_id=opp_id,
            ecrm_id=source.ecrm_id,
            status="resolving" if source.ucm_id else "intake",
            name=source.headline,
            source=IntakeSource(
                channel=source.channel,
                consultant=source.consultant,
                received_at=source.received_at,
                raw_artifacts=list(source.raw_artifacts),
            ),
            client=ClientResolution(
                ucm_id=source.ucm_id,
                ucm_snapshot_version="ucm_v2026.05.13",
                legal_name=source.prospect_legal_name,
                domicile=source.prospect_domicile,
                client_segment=source.client_segment,
                entity_tree_roles=list(source.entity_tree_roles),
                kyc_status="complete" if source.ucm_id else "new_entity_in_progress",
                confidence=0.95 if source.ucm_id else 0.0,
            ),
            relationship=RelationshipContext(
                existing_revenue_usd_annual=source.existing_revenue_usd_annual,
                existing_products=list(source.existing_products),
                cross_sell_pipeline=list(source.cross_sell_pipeline),
                rm_user_id=source.rm_user_id,
                exec_sponsor_user_id=source.exec_sponsor_user_id,
            ),
            scope_summary=ScopeSummary(
                products_requested=list(source.products_requested),
                jurisdictions=list(source.jurisdictions),
                estimated_aum_usd=source.estimated_aum_usd,
                indicative_go_live=source.indicative_go_live,
                nav_strikes_per_day=source.nav_strikes_per_day,
                transactions_per_year=source.transactions_per_year,
                capital_events_per_year=source.capital_events_per_year,
                shareholders=source.shareholders,
            ),
            source_id=source.source_id,
        )
        self.opp_upsert(opp)
        source.state = "promoted"
        source.promoted_opportunity_id = opp_id
        source.promoted_at = now_iso()
        self.source_upsert(source)
        self.journal_append(opp_id, "intake",
                            {"channel": source.channel, "consultant": source.consultant,
                             "received_at": source.received_at, "source_id": source.source_id})
        self.journal_append(opp_id, "source.promote",
                            {"source_id": source.source_id, "ecrm_id": source.ecrm_id})
        if source.ucm_id:
            self.journal_append(opp_id, "resolve",
                                {"ucm_id": source.ucm_id, "confidence": 0.95})
        return opp

    def source_decline(self, source_id: str, reason: str) -> EcrmSource:
        source = self.source_get(source_id)
        if source is None:
            raise KeyError(f"Source not found: {source_id}")
        source.state = "declined"
        source.notes = (source.notes + " · " if source.notes else "") + f"declined: {reason}"
        self.source_upsert(source)
        return source

    # ────────────────── Lifecycle helpers ──────────────────

    # Maps current status → (label, callable). Calling the action runs the
    # deterministic engine for the next stage and (because engines update
    # opp.status themselves) advances the lifecycle by one step.
    _ADVANCE_PLAN: list[tuple[str, str]] = [
        ("intake",          "scope_compute"),
        ("resolving",       "scope_compute"),
        ("scoping",         "complexity_score"),
        ("ddq",             "complexity_score"),
        ("complexity",      "cost_compute"),
        ("cost_capacity",   "pricing_propose"),
        ("pricing",         "operating_model_design"),
        ("operating_model", "approval_request"),
        # approval → seal handled by approval_decide path
    ]

    def advance(self, opp_id: OpportunityId) -> Opportunity:
        """Run the deterministic engine that takes the opp to the next stage.

        Idempotent: if the current stage's artifact already exists but status
        hasn't moved (e.g. user clicked advance after re-running), the engine
        runs again to refresh.
        """
        opp = self.opp_get(opp_id)
        if opp is None:
            raise KeyError(f"Opportunity not found: {opp_id}")
        if opp.status in ("won", "lost", "withdrawn"):
            raise ValueError(f"Opportunity is in terminal status '{opp.status}' — cannot advance")
        # Need capacity before cost; engines depend on prior outputs being present
        # so we ensure the chain is filled before running the named engine.
        if opp.status == "complexity" and self.capacity_for(opp_id) is None:
            self.capacity_compute(opp_id)
        method_name = next((m for s, m in self._ADVANCE_PLAN if s == opp.status), None)
        if method_name is None:
            # Approval → seal: caller should explicitly call approval_decide + seal.
            raise ValueError(f"No advance path from status '{opp.status}' — "
                             "submit approval decisions then call /seal")
        before = opp.status
        getattr(self, method_name)(opp_id)
        # cost_compute leaves status="cost_capacity"; downstream gates expect
        # capacity to be present alongside.
        if method_name == "cost_compute" and self.capacity_for(opp_id) is None:
            self.capacity_compute(opp_id)
        after = self.opp_get(opp_id)
        self.journal_append(opp_id, "advance",
                            {"from": before, "to": after.status if after else "?",
                             "engine": method_name})
        return after  # type: ignore[return-value]

    def dispose(self, opp_id: OpportunityId, state: str, reason: str) -> Opportunity:
        if state not in ("lost", "withdrawn"):
            raise ValueError(f"Invalid disposition state: {state}")
        opp = self.opp_get(opp_id)
        if opp is None:
            raise KeyError(f"Opportunity not found: {opp_id}")
        opp.status = state   # type: ignore[assignment]
        opp.disposition_reason = reason
        opp.disposition_at = now_iso()
        self.opp_upsert(opp)
        self.journal_append(opp_id, "disposition",
                            {"state": state, "reason": reason})
        return opp

    # ────────────────── Seeded fixtures ──────────────────

    def _seed(self) -> None:
        """Realistic opportunities at every lifecycle stage + eCRM source inbox.

        Idempotent: skips any opp_id / source_id already present so the seed
        can run again after the `.seeded` marker is removed without clobbering
        operator-created state.
        """
        self._seed_sources()
        self._seed_opportunities()

    def _seed_opportunities(self) -> None:
        # 1. Acme Pension — asset owner, in intake
        if self.opp_get("opp_acme_pension_eu"):
            self._seed_extended()
            return
        opp1 = Opportunity(
            opportunity_id="opp_acme_pension_eu",
            ecrm_id="006-ACME-2026-Q2",
            status="intake",
            name="Acme Pension EU — Global Custody + UCITS NAV",
            source=IntakeSource(
                channel="rfp_email",
                received_at="2026-05-08T14:22:00+00:00",
                raw_artifacts=["s3://bny-rfp/acme-pension-2026q2.pdf"],
            ),
            client=ClientResolution(
                ucm_id="ucm_acme_pension_group",
                ucm_snapshot_version="ucm_v2026.05.13",
                legal_name="Acme Pension Group BV",
                domicile="NL",
                client_segment="asset_owner_pension",
                entity_tree_roles=[
                    EntityTreeRole("plan_sponsor", "ucm_acme_pension_group", "Acme Pension Group BV"),
                    EntityTreeRole("fund_umbrella", "ucm_acme_pension_ucits", "Acme UCITS Umbrella"),
                    EntityTreeRole("sub_fund", "ucm_acme_global_eq", "Acme Global Equity"),
                    EntityTreeRole("sub_fund", "ucm_acme_em_debt", "Acme EM Debt"),
                ],
                kyc_status="complete",
                confidence=0.96,
            ),
            relationship=RelationshipContext(
                existing_revenue_usd_annual=4_200_000,
                existing_products=["custody.global"],
                cross_sell_pipeline=["fx.standing_instruction"],
                rm_user_id="u_rm_anna",
                exec_sponsor_user_id="u_es_dirk",
            ),
            scope_summary=ScopeSummary(
                products_requested=["custody.global", "fa.daily_nav", "depo.ucits",
                                    "fadmin.regulatory_reporting.ucits", "fx.standing_instruction"],
                jurisdictions=["IE", "LU"],
                estimated_aum_usd=42_000_000_000,
                indicative_go_live="2027-01-01",
                nav_strikes_per_day=18,
                transactions_per_year=480_000,
                capital_events_per_year=120,
                shareholders=78_000,
            ),
        )
        self.opp_upsert(opp1)
        self.journal_append(opp1.opportunity_id, "intake",
                            {"channel": "rfp_email", "received_at": opp1.source.received_at})
        self.journal_append(opp1.opportunity_id, "resolve",
                            {"ucm_id": opp1.client.ucm_id, "confidence": opp1.client.confidence})

        # 2. Pinnacle AM — asset manager, full pipeline through pricing
        opp2 = Opportunity(
            opportunity_id="opp_pinnacle_am_global",
            ecrm_id="006-PINNACLE-2026-Q1",
            status="scoping",
            name="Pinnacle Asset Management — Global UCITS + Alts",
            source=IntakeSource(
                channel="consultant",
                consultant="bfinance",
                received_at="2026-04-15T09:00:00+00:00",
                raw_artifacts=["s3://bny-rfp/pinnacle-bfinance.docx",
                               "s3://bny-rfp/pinnacle-ddq-afme.xlsx"],
            ),
            client=ClientResolution(
                ucm_id="ucm_pinnacle_group",
                ucm_snapshot_version="ucm_v2026.05.13",
                legal_name="Pinnacle Asset Management Group Ltd",
                domicile="UK",
                client_segment="asset_manager",
                entity_tree_roles=[
                    EntityTreeRole("manco", "ucm_pinnacle_manco_ie", "Pinnacle ManCo Ireland Ltd"),
                    EntityTreeRole("aifm", "ucm_pinnacle_aifm_lu", "Pinnacle AIFM Lux"),
                    EntityTreeRole("fund_umbrella", "ucm_pinnacle_ucits", "Pinnacle UCITS ICAV"),
                    EntityTreeRole("fund_umbrella", "ucm_pinnacle_alts", "Pinnacle Alts SCSp"),
                    EntityTreeRole("sub_fund", "ucm_pinnacle_global_eq", "Pinnacle Global Equity"),
                    EntityTreeRole("sub_fund", "ucm_pinnacle_alts_pe1", "Pinnacle PE Fund I"),
                ],
                kyc_status="complete",
                confidence=0.92,
            ),
            relationship=RelationshipContext(
                existing_revenue_usd_annual=0,
                existing_products=[],
                cross_sell_pipeline=["seclen.agency", "fx.standing_instruction"],
                rm_user_id="u_rm_bert",
                exec_sponsor_user_id="u_es_clarice",
            ),
            scope_summary=ScopeSummary(
                products_requested=["custody.global", "fa.daily_nav", "fa.multi_class",
                                    "depo.ucits", "fadmin.regulatory_reporting.ucits",
                                    "alts.pe_admin", "ta.dublin", "moo.ibor",
                                    "seclen.agency", "fx.standing_instruction",
                                    "conn.nexen_portal"],
                jurisdictions=["IE", "LU"],
                estimated_aum_usd=85_000_000_000,
                indicative_go_live="2027-04-01",
                nav_strikes_per_day=42,
                transactions_per_year=1_250_000,
                capital_events_per_year=480,
                shareholders=185_000,
            ),
        )
        self.opp_upsert(opp2)
        self.journal_append(opp2.opportunity_id, "intake", {"channel": "consultant"})
        self.journal_append(opp2.opportunity_id, "resolve", {"ucm_id": opp2.client.ucm_id})
        self.scope_compute(opp2.opportunity_id)
        # Seed example DDQ commitments
        run_id = "run_pinnacle_ddq_2026q2"
        commits = [
            Commitment(
                commitment_id=f"cmt_{_ulid()}",
                opportunity_id=opp2.opportunity_id,
                ddq_run_id=run_id,
                canonical_id="canon.or.business_continuity.rto",
                library_entry_hash="sha256:placeholder_rto",
                commitment_text="RTO for core fund accounting platform is 4 hours; RPO 15 minutes.",
                commitment_class="sla",
                material=True,
                contract_schedule_target="schedule_b.sla",
            ),
            Commitment(
                commitment_id=f"cmt_{_ulid()}",
                opportunity_id=opp2.opportunity_id,
                ddq_run_id=run_id,
                canonical_id="canon.is.iam.iam_04",
                library_entry_hash="sha256:placeholder_iam",
                commitment_text="MFA required for all privileged production access. SOC 2 Type II + ISAE 3402.",
                commitment_class="control",
                material=True,
                contract_schedule_target="schedule_c.controls",
            ),
            Commitment(
                commitment_id=f"cmt_{_ulid()}",
                opportunity_id=opp2.opportunity_id,
                ddq_run_id=run_id,
                canonical_id="canon.reg.gdpr.eu_residency",
                library_entry_hash="sha256:placeholder_residency",
                commitment_text="Client EU resident data held within EEA (Ireland + Luxembourg).",
                commitment_class="data_residency",
                material=True,
                contract_schedule_target="schedule_d.data_residency",
            ),
        ]
        self.commitments_set(opp2.opportunity_id, commits)
        self.complexity_score(opp2.opportunity_id)
        self.capacity_compute(opp2.opportunity_id)
        self.cost_compute(opp2.opportunity_id)
        self.pricing_propose(opp2.opportunity_id)

        # 3. Heritage Alts — alts manager, sealed deal
        opp3 = Opportunity(
            opportunity_id="opp_heritage_alts",
            ecrm_id="006-HERITAGE-2026-Q1",
            status="cost_capacity",
            name="Heritage Alternatives — PE Admin + Custody",
            source=IntakeSource(
                channel="rm_submitted",
                received_at="2026-03-10T11:30:00+00:00",
                raw_artifacts=[],
            ),
            client=ClientResolution(
                ucm_id="ucm_heritage_alts",
                ucm_snapshot_version="ucm_v2026.05.13",
                legal_name="Heritage Alternatives LLC",
                domicile="US",
                client_segment="alts_manager",
                entity_tree_roles=[
                    EntityTreeRole("manco", "ucm_heritage_manco", "Heritage GP LLC"),
                    EntityTreeRole("fund_umbrella", "ucm_heritage_pe", "Heritage PE Fund III"),
                ],
                kyc_status="complete",
                confidence=0.99,
            ),
            relationship=RelationshipContext(
                existing_revenue_usd_annual=1_800_000,
                existing_products=["custody.global"],
                cross_sell_pipeline=["fx.standing_instruction"],
            ),
            scope_summary=ScopeSummary(
                products_requested=["custody.global", "alts.pe_admin"],
                jurisdictions=["IE", "KY"],
                estimated_aum_usd=3_500_000_000,
                indicative_go_live="2027-07-01",
                nav_strikes_per_day=1,
                transactions_per_year=12_000,
                capital_events_per_year=85,
                shareholders=240,
            ),
        )
        self.opp_upsert(opp3)
        self.journal_append(opp3.opportunity_id, "intake", {"channel": "rm_submitted"})
        self.journal_append(opp3.opportunity_id, "resolve", {"ucm_id": opp3.client.ucm_id})
        self.scope_compute(opp3.opportunity_id)
        self.complexity_score(opp3.opportunity_id)
        self.capacity_compute(opp3.opportunity_id)
        self.cost_compute(opp3.opportunity_id)

        # Move opp_pinnacle through to operating_model so the demo has one
        # opportunity that is ready for approval.
        self.operating_model_design("opp_pinnacle_am_global")

        # And finally the extended fixtures — opps at the remaining lifecycle
        # states (ddq, approval, won, lost, withdrawn). Wrapped in a separate
        # method so additions to the lifecycle can be re-seeded idempotently.
        self._seed_extended()

    def _seed_extended(self) -> None:
        """Fill out the lifecycle: ddq / approval / won / lost / withdrawn.

        Each block is guarded by an opp_get check so re-running the seed adds
        only what's missing.
        """
        # 4. Meridian Insurance — re-tender, DDQ in flight, mid-commitment.
        if not self.opp_get("opp_meridian_insurance"):
            opp = Opportunity(
                opportunity_id="opp_meridian_insurance",
                ecrm_id="006-MERIDIAN-2026-RT",
                status="ddq",
                name="Meridian Insurance — Retender · Custody + Reg Reporting",
                source=IntakeSource(
                    channel="retender",
                    received_at="2026-03-22T08:15:00+00:00",
                    raw_artifacts=["s3://bny-rfp/meridian-retender-2026.pdf"],
                ),
                client=ClientResolution(
                    ucm_id="ucm_meridian_ins",
                    ucm_snapshot_version="ucm_v2026.05.13",
                    legal_name="Meridian Life Assurance plc",
                    domicile="IE",
                    client_segment="insurance",
                    entity_tree_roles=[
                        EntityTreeRole("plan_sponsor", "ucm_meridian_ins", "Meridian Life Assurance plc"),
                        EntityTreeRole("mandate", "ucm_meridian_general_account", "Meridian General Account"),
                        EntityTreeRole("mandate", "ucm_meridian_with_profits", "Meridian With-Profits Fund"),
                    ],
                    kyc_status="complete",
                    confidence=0.98,
                ),
                relationship=RelationshipContext(
                    existing_revenue_usd_annual=6_800_000,
                    existing_products=["custody.global", "fadmin.regulatory_reporting.ucits"],
                    cross_sell_pipeline=["fx.standing_instruction", "seclen.agency"],
                    rm_user_id="u_rm_maeve",
                    exec_sponsor_user_id="u_es_dirk",
                ),
                scope_summary=ScopeSummary(
                    products_requested=["custody.global", "fa.daily_nav",
                                        "fadmin.regulatory_reporting.ucits", "depo.ucits",
                                        "fx.standing_instruction", "conn.nexen_portal"],
                    jurisdictions=["IE", "LU"],
                    estimated_aum_usd=28_000_000_000,
                    indicative_go_live="2027-06-01",
                    nav_strikes_per_day=22,
                    transactions_per_year=620_000,
                    capital_events_per_year=210,
                    shareholders=120_000,
                ),
            )
            self.opp_upsert(opp)
            self.journal_append(opp.opportunity_id, "intake", {"channel": "retender"})
            self.journal_append(opp.opportunity_id, "resolve",
                                {"ucm_id": opp.client.ucm_id, "confidence": 0.98})
            self.scope_compute(opp.opportunity_id)
            self.commitments_set(opp.opportunity_id, [
                Commitment(
                    commitment_id=f"cmt_{_ulid()}",
                    opportunity_id=opp.opportunity_id,
                    ddq_run_id="run_meridian_ddq_2026",
                    canonical_id="canon.or.business_continuity.rto",
                    library_entry_hash="sha256:placeholder_rto",
                    commitment_text="RTO 2 hours for daily NAV strike; RPO 5 minutes.",
                    commitment_class="sla", material=True,
                    contract_schedule_target="schedule_b.sla",
                ),
                Commitment(
                    commitment_id=f"cmt_{_ulid()}",
                    opportunity_id=opp.opportunity_id,
                    ddq_run_id="run_meridian_ddq_2026",
                    canonical_id="canon.reg.solvency_ii.qrt",
                    library_entry_hash="sha256:placeholder_qrt",
                    commitment_text="Quarterly Solvency II QRT pack delivered by working day 12.",
                    commitment_class="reporting", material=True,
                    contract_schedule_target="schedule_e.reporting",
                ),
            ])
            opp = self.opp_get(opp.opportunity_id)
            if opp:
                opp.status = "ddq"
                self.opp_upsert(opp)

        # 5. Pinnacle is already at operating_model. Request approval and seed
        # one approval decision so an opp sits mid-approval committee.
        try:
            if (self.approval_for("opp_pinnacle_am_global") is None
                    and (om := self.operating_model_for("opp_pinnacle_am_global")) is not None
                    and not om.has_unmet_commitments):
                self.approval_request("opp_pinnacle_am_global")
                self.approval_decide("opp_pinnacle_am_global",
                                     role="segment_head", user_id="u_seg_irene",
                                     comment="Strategic priority; pricing acceptable.")
        except Exception:
            pass

        # 6. Kingsbridge — fully sealed deal (won).
        if not self.opp_get("opp_kingsbridge_custody"):
            opp = Opportunity(
                opportunity_id="opp_kingsbridge_custody",
                ecrm_id="006-KINGSBRIDGE-2025-Q4",
                status="operating_model",
                name="Kingsbridge Asset Servicing — UK Custody + TA",
                source=IntakeSource(
                    channel="rm_submitted",
                    received_at="2025-11-14T09:00:00+00:00",
                    raw_artifacts=["s3://bny-rfp/kingsbridge-mandate.pdf"],
                ),
                client=ClientResolution(
                    ucm_id="ucm_kingsbridge",
                    ucm_snapshot_version="ucm_v2026.05.13",
                    legal_name="Kingsbridge Asset Management Ltd",
                    domicile="UK",
                    client_segment="asset_manager",
                    entity_tree_roles=[
                        EntityTreeRole("manco", "ucm_kingsbridge_manco_ie", "Kingsbridge ManCo Ireland Ltd"),
                        EntityTreeRole("fund_umbrella", "ucm_kingsbridge_ucits", "Kingsbridge UCITS ICAV"),
                        EntityTreeRole("sub_fund", "ucm_kingsbridge_uk_eq", "Kingsbridge UK Equity"),
                    ],
                    kyc_status="complete",
                    confidence=0.97,
                ),
                relationship=RelationshipContext(
                    existing_revenue_usd_annual=2_100_000,
                    existing_products=["custody.global"],
                    cross_sell_pipeline=[],
                    rm_user_id="u_rm_george",
                    exec_sponsor_user_id="u_es_clarice",
                ),
                scope_summary=ScopeSummary(
                    products_requested=["custody.global", "fa.daily_nav",
                                        "fadmin.regulatory_reporting.ucits",
                                        "depo.ucits", "ta.dublin", "conn.nexen_portal"],
                    jurisdictions=["IE"],
                    estimated_aum_usd=15_500_000_000,
                    indicative_go_live="2026-10-01",
                    nav_strikes_per_day=12,
                    transactions_per_year=260_000,
                    capital_events_per_year=90,
                    shareholders=42_000,
                ),
            )
            self.opp_upsert(opp)
            self.journal_append(opp.opportunity_id, "intake", {"channel": "rm_submitted"})
            self.journal_append(opp.opportunity_id, "resolve", {"ucm_id": opp.client.ucm_id})
            self.scope_compute(opp.opportunity_id)
            self.commitments_set(opp.opportunity_id, [
                Commitment(
                    commitment_id=f"cmt_{_ulid()}",
                    opportunity_id=opp.opportunity_id,
                    ddq_run_id="run_kingsbridge_ddq_2025",
                    canonical_id="canon.or.business_continuity.rto",
                    library_entry_hash="sha256:placeholder_rto",
                    commitment_text="RTO 4h fund accounting; RPO 15 minutes.",
                    commitment_class="sla", material=True,
                    contract_schedule_target="schedule_b.sla",
                ),
            ])
            self.complexity_score(opp.opportunity_id)
            self.capacity_compute(opp.opportunity_id)
            self.cost_compute(opp.opportunity_id)
            self.pricing_propose(opp.opportunity_id)
            self.operating_model_design(opp.opportunity_id)
            try:
                self.approval_request(opp.opportunity_id)
                appr = self.approval_for(opp.opportunity_id)
                if appr is not None:
                    for role in appr.approvers_required:
                        self.approval_decide(opp.opportunity_id, role=role,
                                             user_id=f"u_{role}_demo",
                                             comment=f"Approved by {role}.")
                    self.seal(opp.opportunity_id)
            except Exception:
                # If guardrails block in some environments, leave it in
                # operating_model — but for the seeded fixture this path
                # is expected to succeed.
                pass

        # 7. Silverline ETF — Lost deal with reason
        if not self.opp_get("opp_silverline_etf"):
            opp = Opportunity(
                opportunity_id="opp_silverline_etf",
                ecrm_id="006-SILVERLINE-2026-Q1",
                status="pricing",
                name="Silverline ETF Capital — Global ETF Services",
                source=IntakeSource(
                    channel="consultant",
                    consultant="mercer",
                    received_at="2026-02-04T13:00:00+00:00",
                    raw_artifacts=["s3://bny-rfp/silverline-mercer.docx"],
                ),
                client=ClientResolution(
                    ucm_id="ucm_silverline",
                    ucm_snapshot_version="ucm_v2026.05.13",
                    legal_name="Silverline ETF Capital LLC",
                    domicile="US",
                    client_segment="asset_manager",
                    entity_tree_roles=[
                        EntityTreeRole("manco", "ucm_silverline_manco", "Silverline ETF GP"),
                        EntityTreeRole("fund_umbrella", "ucm_silverline_etf_umb", "Silverline ETF Trust"),
                    ],
                    kyc_status="complete",
                    confidence=0.94,
                ),
                relationship=RelationshipContext(
                    existing_revenue_usd_annual=0,
                    existing_products=[],
                    cross_sell_pipeline=["fx.standing_instruction"],
                    rm_user_id="u_rm_jonas",
                ),
                scope_summary=ScopeSummary(
                    products_requested=["custody.global", "fa.daily_nav",
                                        "fa.multi_class", "fx.standing_instruction"],
                    jurisdictions=["IE", "LU"],
                    estimated_aum_usd=9_200_000_000,
                    indicative_go_live="2026-12-01",
                    nav_strikes_per_day=28,
                    transactions_per_year=410_000,
                    capital_events_per_year=140,
                    shareholders=58_000,
                ),
            )
            self.opp_upsert(opp)
            self.journal_append(opp.opportunity_id, "intake", {"channel": "consultant"})
            self.journal_append(opp.opportunity_id, "resolve", {"ucm_id": opp.client.ucm_id})
            self.scope_compute(opp.opportunity_id)
            self.complexity_score(opp.opportunity_id)
            self.capacity_compute(opp.opportunity_id)
            self.cost_compute(opp.opportunity_id)
            self.pricing_propose(opp.opportunity_id)
            self.dispose(opp.opportunity_id, "lost",
                         "Awarded to incumbent on pricing — competitor 1.1bp vs our 1.6bp floor.")

        # 8. Polaris Sovereign — Withdrawn (scope conflict)
        if not self.opp_get("opp_polaris_sovereign"):
            opp = Opportunity(
                opportunity_id="opp_polaris_sovereign",
                ecrm_id="006-POLARIS-2026-Q1",
                status="scoping",
                name="Polaris Sovereign Fund — Global Custody + Sec Lending",
                source=IntakeSource(
                    channel="cross_segment",
                    received_at="2026-01-12T11:00:00+00:00",
                    raw_artifacts=["s3://bny-rfp/polaris-intro.pdf"],
                ),
                client=ClientResolution(
                    ucm_id="ucm_polaris_sw",
                    ucm_snapshot_version="ucm_v2026.05.13",
                    legal_name="Polaris Sovereign Investment Authority",
                    domicile="SG",
                    client_segment="sovereign",
                    entity_tree_roles=[
                        EntityTreeRole("plan_sponsor", "ucm_polaris_sw", "Polaris SIA"),
                        EntityTreeRole("mandate", "ucm_polaris_eq", "Polaris Equities Mandate"),
                        EntityTreeRole("mandate", "ucm_polaris_fi", "Polaris Fixed Income Mandate"),
                    ],
                    kyc_status="complete",
                    confidence=0.91,
                ),
                relationship=RelationshipContext(
                    existing_revenue_usd_annual=0,
                    existing_products=[],
                    cross_sell_pipeline=[],
                    rm_user_id="u_rm_kavi",
                    exec_sponsor_user_id="u_es_marcus",
                ),
                scope_summary=ScopeSummary(
                    products_requested=["custody.global", "seclen.agency",
                                        "fx.standing_instruction", "moo.ibor"],
                    jurisdictions=["SG", "UK", "US"],
                    estimated_aum_usd=120_000_000_000,
                    indicative_go_live="2027-06-01",
                    nav_strikes_per_day=0,
                    transactions_per_year=950_000,
                    capital_events_per_year=200,
                    shareholders=0,
                ),
            )
            self.opp_upsert(opp)
            self.journal_append(opp.opportunity_id, "intake", {"channel": "cross_segment"})
            self.journal_append(opp.opportunity_id, "resolve", {"ucm_id": opp.client.ucm_id})
            self.scope_compute(opp.opportunity_id)
            self.dispose(opp.opportunity_id, "withdrawn",
                         "Client paused sourcing pending internal restructure; "
                         "expected to relaunch H2 2027.")

        # 9. Ardent Alts — high-tier alts manager, approval in flight
        if not self.opp_get("opp_ardent_alts"):
            opp = Opportunity(
                opportunity_id="opp_ardent_alts",
                ecrm_id="006-ARDENT-2026-Q1",
                status="operating_model",
                name="Ardent Alts — Private Credit + PE Admin",
                source=IntakeSource(
                    channel="consultant",
                    consultant="cambridge",
                    received_at="2026-02-20T10:30:00+00:00",
                    raw_artifacts=["s3://bny-rfp/ardent-cambridge.docx"],
                ),
                client=ClientResolution(
                    ucm_id="ucm_ardent",
                    ucm_snapshot_version="ucm_v2026.05.13",
                    legal_name="Ardent Alternatives Group LP",
                    domicile="KY",
                    client_segment="alts_manager",
                    entity_tree_roles=[
                        EntityTreeRole("manco", "ucm_ardent_gp", "Ardent GP Ltd"),
                        EntityTreeRole("fund_umbrella", "ucm_ardent_pc", "Ardent Private Credit Master"),
                        EntityTreeRole("fund_umbrella", "ucm_ardent_pe", "Ardent PE Fund V"),
                        EntityTreeRole("sub_fund", "ucm_ardent_pc_feeder", "Ardent Private Credit Feeder"),
                    ],
                    kyc_status="complete",
                    confidence=0.93,
                ),
                relationship=RelationshipContext(
                    existing_revenue_usd_annual=0,
                    existing_products=[],
                    cross_sell_pipeline=["seclen.agency"],
                    rm_user_id="u_rm_nora",
                    exec_sponsor_user_id="u_es_clarice",
                ),
                scope_summary=ScopeSummary(
                    products_requested=["custody.global", "alts.pe_admin",
                                        "fa.daily_nav", "depo.aifmd", "fx.standing_instruction"],
                    jurisdictions=["IE", "LU", "KY"],
                    estimated_aum_usd=18_500_000_000,
                    indicative_go_live="2027-01-01",
                    nav_strikes_per_day=4,
                    transactions_per_year=85_000,
                    capital_events_per_year=320,
                    shareholders=1_800,
                ),
            )
            self.opp_upsert(opp)
            self.journal_append(opp.opportunity_id, "intake", {"channel": "consultant"})
            self.journal_append(opp.opportunity_id, "resolve", {"ucm_id": opp.client.ucm_id})
            self.scope_compute(opp.opportunity_id)
            self.commitments_set(opp.opportunity_id, [
                Commitment(
                    commitment_id=f"cmt_{_ulid()}",
                    opportunity_id=opp.opportunity_id,
                    ddq_run_id="run_ardent_ddq_2026",
                    canonical_id="canon.or.business_continuity.rto",
                    library_entry_hash="sha256:placeholder_rto",
                    commitment_text="RTO 6 hours for PE admin platform; RPO 30 minutes.",
                    commitment_class="sla", material=True,
                    contract_schedule_target="schedule_b.sla",
                ),
                Commitment(
                    commitment_id=f"cmt_{_ulid()}",
                    opportunity_id=opp.opportunity_id,
                    ddq_run_id="run_ardent_ddq_2026",
                    canonical_id="canon.is.iam.iam_04",
                    library_entry_hash="sha256:placeholder_iam",
                    commitment_text="Investor portal MFA + just-in-time access for limited partners.",
                    commitment_class="control", material=True,
                    contract_schedule_target="schedule_c.controls",
                ),
            ])
            self.complexity_score(opp.opportunity_id)
            self.capacity_compute(opp.opportunity_id)
            self.cost_compute(opp.opportunity_id)
            self.pricing_propose(opp.opportunity_id)
            self.operating_model_design(opp.opportunity_id)
            try:
                self.approval_request(opp.opportunity_id)
            except Exception:
                pass

    # ────────────────── eCRM source inbox seeds ──────────────────

    def _seed_sources(self) -> None:
        defaults: list[EcrmSource] = [
            EcrmSource(
                source_id="src_globalpath_pension",
                ecrm_id="006-GLOBALPATH-2026-NEW",
                received_at="2026-05-10T09:14:00+00:00",
                channel="rfp_email",
                headline="GlobalPath Pension Fund — UK + Ireland Custody RFP",
                prospect_legal_name="GlobalPath Pension Trustees Ltd",
                prospect_domicile="UK",
                client_segment="asset_owner_pension",
                ucm_id="ucm_globalpath",
                rm_user_id="u_rm_anna",
                exec_sponsor_user_id="u_es_dirk",
                products_requested=["custody.global", "fa.daily_nav",
                                    "fadmin.regulatory_reporting.ucits",
                                    "depo.ucits", "fx.standing_instruction"],
                jurisdictions=["IE", "UK"],
                estimated_aum_usd=22_000_000_000,
                indicative_go_live="2027-04-01",
                nav_strikes_per_day=14,
                transactions_per_year=320_000,
                capital_events_per_year=85,
                shareholders=46_000,
                raw_artifacts=["s3://bny-rfp/globalpath-pension-rfp.pdf",
                               "s3://bny-rfp/globalpath-ddq-sig-core.xlsx"],
                existing_revenue_usd_annual=0,
                cross_sell_pipeline=["seclen.agency"],
                entity_tree_roles=[
                    EntityTreeRole("plan_sponsor", "ucm_globalpath", "GlobalPath Pension Trustees Ltd"),
                    EntityTreeRole("mandate", "ucm_globalpath_eq", "GlobalPath Equity Mandate"),
                    EntityTreeRole("mandate", "ucm_globalpath_fi", "GlobalPath Fixed Income Mandate"),
                ],
                notes="bfinance-style RFP; Q4 2026 decision target.",
                state="new",
            ),
            EcrmSource(
                source_id="src_summit_capital",
                ecrm_id="006-SUMMIT-2026-CON",
                received_at="2026-05-06T16:40:00+00:00",
                channel="consultant",
                consultant="aon",
                headline="Summit Capital Partners — Hedge Fund Admin (new entity)",
                prospect_legal_name="Summit Capital Partners LP",
                prospect_domicile="KY",
                client_segment="alts_manager",
                ucm_id=None,                  # net-new entity — needs KYC kickoff
                rm_user_id="u_rm_jonas",
                products_requested=["custody.global", "alts.hedge_admin",
                                    "fa.daily_nav", "fx.standing_instruction"],
                jurisdictions=["KY", "IE"],
                estimated_aum_usd=4_800_000_000,
                indicative_go_live="2027-03-01",
                nav_strikes_per_day=3,
                transactions_per_year=42_000,
                capital_events_per_year=180,
                shareholders=620,
                raw_artifacts=["s3://bny-rfp/summit-aon-rfp.docx"],
                notes="Net-new entity — KYC kickoff required.",
                state="new",
            ),
            EcrmSource(
                source_id="src_atlas_wealth",
                ecrm_id="006-ATLAS-2026-XSEG",
                received_at="2026-05-09T11:00:00+00:00",
                channel="cross_segment",
                headline="Atlas Wealth — Pershing referral · UMA custody scaling",
                prospect_legal_name="Atlas Wealth Advisors LLC",
                prospect_domicile="US",
                client_segment="asset_manager",
                ucm_id="ucm_atlas_wealth",
                rm_user_id="u_rm_george",
                exec_sponsor_user_id="u_es_clarice",
                products_requested=["custody.global", "fa.daily_nav",
                                    "ta.us", "conn.nexen_portal"],
                jurisdictions=["US"],
                estimated_aum_usd=6_400_000_000,
                indicative_go_live="2027-01-01",
                nav_strikes_per_day=8,
                transactions_per_year=210_000,
                capital_events_per_year=40,
                shareholders=92_000,
                raw_artifacts=[],
                existing_revenue_usd_annual=420_000,
                existing_products=["custody.global"],
                cross_sell_pipeline=["fx.standing_instruction"],
                entity_tree_roles=[
                    EntityTreeRole("manco", "ucm_atlas_wealth", "Atlas Wealth Advisors LLC"),
                ],
                notes="Pershing flagged this as referral; existing custody book.",
                state="new",
            ),
            EcrmSource(
                source_id="src_keystone_rt",
                ecrm_id="006-KEYSTONE-2026-RT",
                received_at="2026-05-02T08:20:00+00:00",
                channel="retender",
                headline="Keystone Endowment — Retender (current TA Lux)",
                prospect_legal_name="Keystone University Endowment",
                prospect_domicile="US",
                client_segment="asset_owner_pension",
                ucm_id="ucm_keystone_endow",
                rm_user_id="u_rm_anna",
                products_requested=["custody.global", "fa.daily_nav",
                                    "ta.lux", "fadmin.regulatory_reporting.ucits"],
                jurisdictions=["LU"],
                estimated_aum_usd=14_200_000_000,
                indicative_go_live="2027-09-01",
                nav_strikes_per_day=10,
                transactions_per_year=180_000,
                capital_events_per_year=60,
                shareholders=18_000,
                raw_artifacts=["s3://bny-rfp/keystone-retender-2026.pdf"],
                existing_revenue_usd_annual=3_200_000,
                existing_products=["custody.global", "ta.lux"],
                cross_sell_pipeline=["seclen.agency"],
                entity_tree_roles=[
                    EntityTreeRole("plan_sponsor", "ucm_keystone_endow", "Keystone University Endowment"),
                    EntityTreeRole("fund_umbrella", "ucm_keystone_lux", "Keystone Lux SICAV"),
                ],
                notes="Existing client; retender to refresh terms.",
                state="triaging",
            ),
            EcrmSource(
                source_id="src_brightside_rm",
                ecrm_id="006-BRIGHTSIDE-2026-RM",
                received_at="2026-05-01T15:10:00+00:00",
                channel="rm_submitted",
                headline="Brightside Insurance — General account custody",
                prospect_legal_name="Brightside Insurance Group",
                prospect_domicile="DE",
                client_segment="insurance",
                ucm_id="ucm_brightside_ins",
                rm_user_id="u_rm_maeve",
                products_requested=["custody.global", "fadmin.regulatory_reporting.ucits",
                                    "fx.standing_instruction"],
                jurisdictions=["DE", "LU"],
                estimated_aum_usd=8_900_000_000,
                indicative_go_live="2027-04-01",
                nav_strikes_per_day=6,
                transactions_per_year=140_000,
                capital_events_per_year=70,
                shareholders=24_000,
                raw_artifacts=[],
                notes="RM Maeve submitting via eCRM; competitive — incumbent is JPM.",
                state="new",
            ),
            EcrmSource(
                source_id="src_horizon_etf",
                ecrm_id="006-HORIZON-2026-WTW",
                received_at="2026-04-28T12:00:00+00:00",
                channel="consultant",
                consultant="wtw",
                headline="Horizon ETF Managers — APAC ETF services build-out",
                prospect_legal_name="Horizon ETF Managers Pte Ltd",
                prospect_domicile="SG",
                client_segment="asset_manager",
                ucm_id=None,
                rm_user_id="u_rm_kavi",
                products_requested=["custody.global", "etf.create_redeem",
                                    "fa.daily_nav", "fx.standing_instruction"],
                jurisdictions=["SG", "HK"],
                estimated_aum_usd=2_100_000_000,
                indicative_go_live="2027-07-01",
                nav_strikes_per_day=5,
                transactions_per_year=85_000,
                capital_events_per_year=30,
                shareholders=12_000,
                raw_artifacts=["s3://bny-rfp/horizon-etf-wtw.pdf"],
                notes="Net-new APAC entity; KYC + regulatory permission scoping required.",
                state="new",
            ),
        ]
        for s in defaults:
            if self.source_get(s.source_id) is None:
                self.source_upsert(s)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _complexity_note(key: str, score: int) -> str:
    notes = {
        "fund_count_structure": ["single fund", "small umbrella", "umbrella + sub-funds", "multi-umbrella", "complex multi-umbrella"],
        "jurisdictional_spread": ["single", "developed only", "EU + 1 EM", "EU + EM mix", "global with frontier"],
        "asset_class_breadth": ["narrow", "core", "core + alts", "alts breadth", "full breadth"],
        "nav_cadence_sla": ["monthly", "weekly", "daily", "intraday", "intraday + ETF"],
        "regulatory_regime_coverage": ["none", "single regime", "UCITS or AIFMD", "UCITS + AIFMD", "global regimes"],
        "bespoke_reporting": ["minimal", "standard", "moderate", "heavy", "fully bespoke"],
        "client_system_integration_footprint": ["none", "single feed", "few", "many", "ecosystem"],
        "transition_aggression": ["relaxed", "standard", "compressed", "aggressive", "extreme"],
        "servicing_model_dedicated_vs_pooled": ["pooled", "mostly pooled", "hybrid", "mostly dedicated", "dedicated"],
        "data_residency_constraints": ["none", "1 region", "EU strict", "EU + APAC strict", "global strict"],
    }
    bucket = notes.get(key, [])
    return bucket[min(score, len(bucket)) - 1] if bucket else ""


def _units_for_load_factor(load_factor: str, scope: ScopeSummary) -> float:
    """Map scope-summary volumes into the same unit basis the app registry
    declares capacity in (per_day metrics vs. absolute counts)."""
    return {
        # daily basis — apps declare capacity per-day
        "per_nav_strike": float(scope.nav_strikes_per_day),
        "per_trade": scope.transactions_per_year / 250.0,
        # absolute counts — derive from AUM where the client didn't tell us
        "per_holding": max(scope.estimated_aum_usd / 1_500_000.0, 200.0),
        "per_user": max(50.0, scope.shareholders * 0.01),
        "per_shareholder": float(scope.shareholders),
        "per_capital_event": scope.capital_events_per_year / 12.0,   # per-month basis
        "per_filing": 60.0,
        "per_position": max(scope.estimated_aum_usd / 3_000_000.0, 100.0),
    }.get(load_factor, 0.0)


def _approvers_for_tier(tier: str) -> list[str]:
    return {
        "tier_1_rm_segment_head": ["rm", "segment_head"],
        "tier_2_segment_head_cfo_delegate": ["segment_head", "as_cfo_delegate"],
        "tier_3_cfo_coo_risk": ["as_cfo", "as_coo", "risk_head"],
        "tier_4_segment_ceo_cfo": ["as_ceo", "as_cfo", "risk_head"],
    }.get(tier, ["segment_head"])


# ────────────────── dict → dataclass helpers ──────────────────

def _opp_from_dict(d: dict) -> Opportunity:
    return Opportunity(
        opportunity_id=d["opportunity_id"],
        ecrm_id=d["ecrm_id"],
        status=d["status"],
        name=d.get("name", ""),
        source=IntakeSource(**d["source"]),
        client=ClientResolution(
            ucm_id=d["client"]["ucm_id"],
            ucm_snapshot_version=d["client"]["ucm_snapshot_version"],
            legal_name=d["client"]["legal_name"],
            domicile=d["client"]["domicile"],
            client_segment=d["client"]["client_segment"],
            entity_tree_roles=[EntityTreeRole(**e) for e in d["client"]["entity_tree_roles"]],
            kyc_status=d["client"]["kyc_status"],
            confidence=d["client"]["confidence"],
        ),
        relationship=RelationshipContext(**d["relationship"]),
        scope_summary=ScopeSummary(**d["scope_summary"]),
        ddq_run_id=d.get("ddq_run_id"),
        scope_manifest_id=d.get("scope_manifest_id"),
        complexity_id=d.get("complexity_id"),
        cost_stack_id=d.get("cost_stack_id"),
        capacity_id=d.get("capacity_id"),
        pricing_id=d.get("pricing_id"),
        operating_model_id=d.get("operating_model_id"),
        deal_id=d.get("deal_id"),
        disposition_reason=d.get("disposition_reason"),
        disposition_at=d.get("disposition_at"),
        source_id=d.get("source_id"),
        created_at=d.get("created_at", now_iso()),
        updated_at=d.get("updated_at", now_iso()),
    )


def _scope_from_dict(d: dict) -> ScopeManifest:
    return ScopeManifest(
        scope_manifest_id=d["scope_manifest_id"],
        opportunity_id=d["opportunity_id"],
        upm_snapshot_version=d["upm_snapshot_version"],
        line_items=[ScopeLineItem(
            upm_code=li["upm_code"],
            label=li["label"],
            jurisdiction=li["jurisdiction"],
            legal_entity=li["legal_entity"],
            delivery_stack=[DeliveryStackEntry(**ds) for ds in li["delivery_stack"]],
            dependencies=list(li.get("dependencies", [])),
        ) for li in d["line_items"]],
        legal_entity_assignment=dict(d["legal_entity_assignment"]),
        derived_app_set=list(d["derived_app_set"]),
        derived_jurisdictions=list(d["derived_jurisdictions"]),
        issues=[ScopeIssue(**i) for i in d["issues"]],
        created_at=d.get("created_at", now_iso()),
    )


def _complexity_from_dict(d: dict) -> ComplexityScorecard:
    return ComplexityScorecard(
        complexity_id=d["complexity_id"],
        opportunity_id=d["opportunity_id"],
        scorecard_version=d["scorecard_version"],
        dimensions=[ComplexityDimensionScore(**x) for x in d["dimensions"]],
        weights=dict(d["weights"]),
        composite_score=d["composite_score"],
        tier=d["tier"],
        rationale_narrative=d["rationale_narrative"],
        scored_at=d.get("scored_at", now_iso()),
        scored_by=d.get("scored_by", "system"),
    )


def _cost_from_dict(d: dict) -> CostStack:
    return CostStack(
        cost_stack_id=d["cost_stack_id"],
        opportunity_id=d["opportunity_id"],
        horizon_years=d["horizon_years"],
        direct_fte=[FteLine(**x) for x in d["direct_fte"]],
        sub_custody_passthrough=[SubCustodyLine(**x) for x in d["sub_custody_passthrough"]],
        technology_run_cost=[TechRunCostLine(**x) for x in d["technology_run_cost"]],
        technology_capacity_expansion=[TechExpansionLine(**x) for x in d["technology_capacity_expansion"]],
        transition_one_time=TransitionOneTime(**d["transition_one_time"]),
        risk_compliance_overhead=[RiskComplianceLine(**x) for x in d["risk_compliance_overhead"]],
        allocated_overhead_pct=d["allocated_overhead_pct"],
        totals=CostTotals(**d["totals"]),
        computed_at=d.get("computed_at", now_iso()),
    )


def _capacity_from_dict(d: dict) -> CapacityImpact:
    return CapacityImpact(
        capacity_impact_id=d["capacity_impact_id"],
        opportunity_id=d["opportunity_id"],
        app_impacts=[AppImpact(**x) for x in d["app_impacts"]],
        blocking_constraints=[BlockingConstraint(**x) for x in d["blocking_constraints"]],
        computed_at=d.get("computed_at", now_iso()),
    )


def _pricing_from_dict(d: dict) -> PricingProposal:
    from core.domain.opp_deal import TransactionalFee
    fs = d["fee_structure"]
    fee_structure = FeeStructure(
        asset_based=[AssetBasedTier(
            asset_class=t["asset_class"],
            tiers=[AssetBandFee(**band) for band in t["tiers"]],
        ) for t in fs["asset_based"]],
        transactional=[TransactionalFee(**x) for x in fs["transactional"]],
        fixed_retainers=[FixedRetainer(**x) for x in fs["fixed_retainers"]],
        passthrough_oop=list(fs["passthrough_oop"]),
        minimum_fee_floor_usd_annual=fs["minimum_fee_floor_usd_annual"],
        term_years=fs["term_years"],
        term_discount_pct=fs["term_discount_pct"],
        bundled_discount_pct=fs["bundled_discount_pct"],
    )
    tcv = d["total_client_value"]
    return PricingProposal(
        pricing_proposal_id=d["pricing_proposal_id"],
        opportunity_id=d["opportunity_id"],
        fee_structure=fee_structure,
        sec_lending=SecLendingShare(**d["sec_lending"]),
        fx_revenue=FxRevenueModel(**d["fx_revenue"]),
        total_client_value=TotalClientValue(
            by_year=[TotalClientValueYear(**y) for y in tcv["by_year"]],
            five_year_total_usd=tcv["five_year_total_usd"],
        ),
        margin_analysis=MarginAnalysis(**d["margin_analysis"]),
        sensitivity=[SensitivityScenario(**x) for x in d["sensitivity"]],
        approval_tier_required=d["approval_tier_required"],
        rationale_narrative=d["rationale_narrative"],
        computed_at=d.get("computed_at", now_iso()),
    )


def _commitment_from_dict(d: dict) -> Commitment:
    return Commitment(**d)


def _opmodel_from_dict(d: dict) -> OperatingModelPlan:
    return OperatingModelPlan(
        operating_model_id=d["operating_model_id"],
        opportunity_id=d["opportunity_id"],
        client_service_layer=ServiceModelLayer(
            model=d["client_service_layer"]["model"],
            named_roles=[NamedRole(**r) for r in d["client_service_layer"]["named_roles"]],
            governance_cadence=[GovernanceForum(**g) for g in d["client_service_layer"]["governance_cadence"]],
            escalation_path=list(d["client_service_layer"]["escalation_path"]),
        ),
        operational_footprint=[FunctionalFootprint(**f) for f in d["operational_footprint"]],
        fte_plan=FtePlan(
            by_year=[FteYearPlan(
                year=y["year"],
                net_new_hires=[HireRequisition(**h) for h in y["net_new_hires"]],
                redeployment_count=y["redeployment_count"],
                total_fte=y["total_fte"],
            ) for y in d["fte_plan"]["by_year"]],
            parallel_running_weeks=d["fte_plan"]["parallel_running_weeks"],
            parallel_running_fte_overhead=d["fte_plan"]["parallel_running_fte_overhead"],
            transition_milestones=[TransitionMilestone(**m) for m in d["fte_plan"]["transition_milestones"]],
        ),
        app_impact=[AppImpactSummary(**a) for a in d["app_impact"]],
        integration_builds=[IntegrationBuild(**i) for i in d["integration_builds"]],
        reporting_builds=[ReportingBuild(**r) for r in d["reporting_builds"]],
        resilience_posture=ResiliencePosture(
            bcp_coverage_per_location=list(d["resilience_posture"]["bcp_coverage_per_location"]),
            single_points_of_failure_added=list(d["resilience_posture"]["single_points_of_failure_added"]),
            rto_rpo_commitments=[RtoRpoCommitment(**r) for r in d["resilience_posture"]["rto_rpo_commitments"]],
        ),
        control_environment=ControlEnvironmentChanges(**d["control_environment"]),
        ddq_commitment_crosscheck=[CommitmentCrosscheck(**c) for c in d["ddq_commitment_crosscheck"]],
        computed_at=d.get("computed_at", now_iso()),
    )


def _approval_from_dict(d: dict) -> ApprovalRequest:
    return ApprovalRequest(
        request_id=d["request_id"],
        opportunity_id=d["opportunity_id"],
        tier_required=d["tier_required"],
        approvers_required=list(d["approvers_required"]),
        decisions=[Approver(**x) for x in d.get("decisions", [])],
        state=d.get("state", "open"),
        created_at=d.get("created_at", now_iso()),
    )


def _source_from_dict(d: dict) -> EcrmSource:
    return EcrmSource(
        source_id=d["source_id"],
        ecrm_id=d["ecrm_id"],
        received_at=d["received_at"],
        channel=d["channel"],
        consultant=d.get("consultant"),
        headline=d.get("headline", ""),
        prospect_legal_name=d.get("prospect_legal_name", ""),
        prospect_domicile=d.get("prospect_domicile", ""),
        client_segment=d.get("client_segment", "asset_manager"),
        ucm_id=d.get("ucm_id"),
        rm_user_id=d.get("rm_user_id"),
        exec_sponsor_user_id=d.get("exec_sponsor_user_id"),
        products_requested=list(d.get("products_requested", [])),
        jurisdictions=list(d.get("jurisdictions", [])),
        estimated_aum_usd=int(d.get("estimated_aum_usd", 0)),
        indicative_go_live=d.get("indicative_go_live"),
        nav_strikes_per_day=int(d.get("nav_strikes_per_day", 0)),
        transactions_per_year=int(d.get("transactions_per_year", 0)),
        capital_events_per_year=int(d.get("capital_events_per_year", 0)),
        shareholders=int(d.get("shareholders", 0)),
        raw_artifacts=list(d.get("raw_artifacts", [])),
        existing_revenue_usd_annual=int(d.get("existing_revenue_usd_annual", 0)),
        existing_products=list(d.get("existing_products", [])),
        cross_sell_pipeline=list(d.get("cross_sell_pipeline", [])),
        entity_tree_roles=[EntityTreeRole(**e) for e in d.get("entity_tree_roles", [])],
        notes=d.get("notes", ""),
        state=d.get("state", "new"),
        promoted_opportunity_id=d.get("promoted_opportunity_id"),
        promoted_at=d.get("promoted_at"),
    )


def _bundle_from_dict(d: dict) -> SealedDealBundle:
    return SealedDealBundle(
        deal_id=d["deal_id"],
        opportunity_id=d["opportunity_id"],
        sealed_at=d["sealed_at"],
        ucm_snapshot_version=d["ucm_snapshot_version"],
        upm_snapshot_version=d["upm_snapshot_version"],
        ddq_run_ids=list(d["ddq_run_ids"]),
        scope_manifest_hash=d["scope_manifest_hash"],
        complexity_scorecard_hash=d["complexity_scorecard_hash"],
        cost_stack_hash=d["cost_stack_hash"],
        capacity_impact_hash=d["capacity_impact_hash"],
        pricing_proposal_hash=d["pricing_proposal_hash"],
        operating_model_plan_hash=d["operating_model_plan_hash"],
        commitment_set_hash=d["commitment_set_hash"],
        approval_chain=[Approver(**x) for x in d["approval_chain"]],
        merkle_root=d["merkle_root"],
        platform_version=d["platform_version"],
        handoff_targets=list(d["handoff_targets"]),
    )
