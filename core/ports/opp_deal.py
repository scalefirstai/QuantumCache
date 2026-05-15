"""
Port protocols for the Opp→Deal platform. Adapters live in infra/adapters/.

All eight stage services are addressable through these protocols; tests
use in-memory or fs-backed adapters, production uses Mongo + S3 + the
real BNY systems (eCRM, UCM, UPM, app registry, role catalogue).
"""

from __future__ import annotations

from typing import Iterable, Optional, Protocol

from core.domain.opp_deal import (
    ApprovalRequest,
    ApprovalRequestId,
    CapacityImpact,
    CapacityImpactId,
    CommitmentSet,
    ComplexityScorecard,
    ComplexityScorecardId,
    CostStack,
    CostStackId,
    DealJournalEvent,
    OperatingModelId,
    OperatingModelPlan,
    Opportunity,
    OpportunityId,
    PricingProposal,
    PricingProposalId,
    ScopeManifest,
    ScopeManifestId,
    SealedDealBundle,
)


class OpportunityRepo(Protocol):
    def upsert(self, opp: Opportunity) -> None: ...
    def get(self, opp_id: OpportunityId) -> Optional[Opportunity]: ...
    def list_all(self) -> Iterable[Opportunity]: ...
    def delete(self, opp_id: OpportunityId) -> bool: ...


class ScopeRepo(Protocol):
    def upsert(self, manifest: ScopeManifest) -> None: ...
    def get(self, scope_id: ScopeManifestId) -> Optional[ScopeManifest]: ...
    def for_opportunity(self, opp_id: OpportunityId) -> Optional[ScopeManifest]: ...


class ComplexityRepo(Protocol):
    def upsert(self, card: ComplexityScorecard) -> None: ...
    def for_opportunity(self, opp_id: OpportunityId) -> Optional[ComplexityScorecard]: ...


class CostRepo(Protocol):
    def upsert(self, stack: CostStack) -> None: ...
    def for_opportunity(self, opp_id: OpportunityId) -> Optional[CostStack]: ...


class CapacityRepo(Protocol):
    def upsert(self, impact: CapacityImpact) -> None: ...
    def for_opportunity(self, opp_id: OpportunityId) -> Optional[CapacityImpact]: ...


class PricingRepo(Protocol):
    def upsert(self, proposal: PricingProposal) -> None: ...
    def for_opportunity(self, opp_id: OpportunityId) -> Optional[PricingProposal]: ...


class OperatingModelRepo(Protocol):
    def upsert(self, plan: OperatingModelPlan) -> None: ...
    def for_opportunity(self, opp_id: OpportunityId) -> Optional[OperatingModelPlan]: ...


class CommitmentRepo(Protocol):
    def upsert(self, cs: CommitmentSet) -> None: ...
    def for_opportunity(self, opp_id: OpportunityId) -> Optional[CommitmentSet]: ...


class ApprovalRepo(Protocol):
    def upsert(self, req: ApprovalRequest) -> None: ...
    def for_opportunity(self, opp_id: OpportunityId) -> Optional[ApprovalRequest]: ...


class DealJournal(Protocol):
    def append(
        self,
        opp_id: OpportunityId,
        kind: str,
        payload: dict,
        actor_id: str = "system",
        actor_role: str = "system",
        actor_kind: str = "system",
    ) -> DealJournalEvent: ...
    def list_for_opportunity(self, opp_id: OpportunityId) -> list[DealJournalEvent]: ...
    def seal(self, opp_id: OpportunityId) -> SealedDealBundle: ...
    def get_sealed(self, opp_id: OpportunityId) -> Optional[SealedDealBundle]: ...
    def verify(self, opp_id: OpportunityId) -> dict: ...


class ProductCatalog(Protocol):
    """Read-only mirror of UPM (Universal Product Master)."""
    def all_codes(self) -> list[str]: ...
    def get(self, upm_code: str) -> Optional[dict]: ...
