"""ApprovalRouter — ddq.md §L06 (rule-based, OPA stand-in).

Maps (canonical_domain, validation_verdict, agent_flags) → SME queue + tier.
The real implementation evaluates Rego policies at infra/adapters/opa.
"""

from __future__ import annotations

from core.ports.agent import Agent, AgentEvent, RunContext
from packages.schemas.agents import (
    ApprovalRouterInput, ApprovalRouterOutput,
)


# canonical_id domain prefix → SME queue, per ddq.md §L08.
DOMAIN_QUEUE = {
    "canon.is":    "infosec",
    "canon.cyber": "cyber",
    "canon.esg":   "esg",
    "canon.reg":   "regulatory",
    "canon.subc":  "ops",
    "canon.or":    "ops",
}

# canonical domain → default tier (ddq.md §L06 tiered routing).
TIER1_PREFIXES = ("canon.reg", "canon.cyber", "canon.is")  # high-risk
TIER3_PREFIXES = ()                                          # no boilerplate domains yet


def _domain_of(canonical_id: str | None) -> str | None:
    if not canonical_id:
        return None
    parts = canonical_id.split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return None


def _classify_tier(canonical_id: str | None) -> str:
    if not canonical_id:
        return "tier2"
    for pref in TIER1_PREFIXES:
        if canonical_id.startswith(pref):
            return "tier1"
    for pref in TIER3_PREFIXES:
        if canonical_id.startswith(pref):
            return "tier3"
    return "tier2"


class ApprovalRouter(Agent):
    name = "ApprovalRouter"
    version = "1.0.0"

    def run(self, agent_input: ApprovalRouterInput, ctx: RunContext) -> ApprovalRouterOutput:
        domain = _domain_of(agent_input.canonical_id)
        queue = DOMAIN_QUEUE.get(domain or "", "ops")
        tier = _classify_tier(agent_input.canonical_id)

        # Decision tree:
        # 1. PII halt or validate halt → halt outright; legal review.
        if agent_input.pii_halt:
            out = ApprovalRouterOutput(
                route="halt", queue="legal",
                tier=tier,  # type: ignore[arg-type]
                rationale="PiiScrubber raised halt — confidentiality risk; legal must review before any further action.",
            )
        elif agent_input.validate_verdict == "halt":
            out = ApprovalRouterOutput(
                route="halt", queue="legal",
                tier=tier,  # type: ignore[arg-type]
                rationale="Validator halted (citation/freshness/scrub guardrail) — legal review.",
            )
        # 2. Freshness stale or consistency drift → SME queue, no auto-approve.
        elif agent_input.freshness_stale:
            out = ApprovalRouterOutput(
                route="sme_queue", queue=queue,
                tier=tier,  # type: ignore[arg-type]
                rationale="FreshnessAuditor flagged stale evidence/entry — SME confirmation required.",
            )
        elif agent_input.consistency_drift:
            out = ApprovalRouterOutput(
                route="sme_queue", queue=queue,
                tier=tier,  # type: ignore[arg-type]
                rationale="ConsistencyChecker flagged drift versus prior shipped responses — SME confirmation required.",
            )
        # 3. Low classify confidence → SME queue.
        elif agent_input.classify_confidence < 0.70:
            out = ApprovalRouterOutput(
                route="sme_queue", queue=queue,
                tier=tier,  # type: ignore[arg-type]
                rationale=f"Classify confidence {agent_input.classify_confidence:.2f} below 0.70 SME threshold.",
            )
        # 4. Tier-1 always SME-approve, even on clean pass.
        elif tier == "tier1":
            out = ApprovalRouterOutput(
                route="sme_queue", queue=queue,
                tier=tier,  # type: ignore[arg-type]
                rationale="Tier-1 canonical (regulatory/security/cyber) always requires SME sign-off.",
            )
        # 5. Clean pass + tier-2 or tier-3 → auto-approve.
        else:
            out = ApprovalRouterOutput(
                route="auto_approve", queue=queue,
                tier=tier,  # type: ignore[arg-type]
                rationale=f"All guardrails pass; tier-{tier[-1]} domain {queue} auto-approves.",
            )

        ctx.emit(AgentEvent.make(self.name, self.version, "agent.ApprovalRouter.result", {
            "route": out.route, "queue": out.queue, "tier": out.tier,
            "canonical_id": agent_input.canonical_id,
            "rationale": out.rationale,
        }))
        return out
