"""ApprovalRouter — ddq.md §L06 (rule-based, OPA stand-in).

With a `RuleRepository` injected, the agent walks active rules ordered by
priority and returns the verdict of the **first** rule that fires. If no
rule matches (or no engine is wired), it falls back to the legacy
hardcoded decision tree.

Rules are configured via `/api/v1/rules` (engine="approval"). The
`then.queue` field can be omitted on rules that intentionally defer queue
selection to the domain map.
"""

from __future__ import annotations

from typing import Optional

from core.domain.rules import apply_rules
from core.ports.agent import Agent, AgentEvent, RunContext
from core.ports.rules import RuleRepository
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
TIER3_PREFIXES: tuple[str, ...] = ()                       # no boilerplate domains yet


def _domain_of(canonical_id: Optional[str]) -> Optional[str]:
    if not canonical_id:
        return None
    parts = canonical_id.split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return None


def _classify_tier(canonical_id: Optional[str]) -> str:
    if not canonical_id:
        return "tier2"
    for pref in TIER1_PREFIXES:
        if canonical_id.startswith(pref):
            return "tier1"
    for pref in TIER3_PREFIXES:
        if canonical_id.startswith(pref):
            return "tier3"
    return "tier2"


def _domain_queue(canonical_id: Optional[str]) -> str:
    return DOMAIN_QUEUE.get(_domain_of(canonical_id) or "", "ops")


def _legacy_route(agent_input: ApprovalRouterInput) -> ApprovalRouterOutput:
    """Pre-rule-engine decision tree. Untouched semantics from agent v1.0.0."""
    queue = _domain_queue(agent_input.canonical_id)
    tier = _classify_tier(agent_input.canonical_id)

    if agent_input.pii_halt:
        return ApprovalRouterOutput(
            route="halt", queue="legal", tier=tier,  # type: ignore[arg-type]
            rationale="PiiScrubber raised halt — confidentiality risk; legal must review before any further action.",
        )
    if agent_input.validate_verdict == "halt":
        return ApprovalRouterOutput(
            route="halt", queue="legal", tier=tier,  # type: ignore[arg-type]
            rationale="Validator halted (citation/freshness/scrub guardrail) — legal review.",
        )
    if agent_input.freshness_stale:
        return ApprovalRouterOutput(
            route="sme_queue", queue=queue, tier=tier,  # type: ignore[arg-type]
            rationale="FreshnessAuditor flagged stale evidence/entry — SME confirmation required.",
        )
    if agent_input.consistency_drift:
        return ApprovalRouterOutput(
            route="sme_queue", queue=queue, tier=tier,  # type: ignore[arg-type]
            rationale="ConsistencyChecker flagged drift versus prior shipped responses — SME confirmation required.",
        )
    if agent_input.classify_confidence < 0.70:
        return ApprovalRouterOutput(
            route="sme_queue", queue=queue, tier=tier,  # type: ignore[arg-type]
            rationale=f"Classify confidence {agent_input.classify_confidence:.2f} below 0.70 SME threshold.",
        )
    if tier == "tier1":
        return ApprovalRouterOutput(
            route="sme_queue", queue=queue, tier=tier,  # type: ignore[arg-type]
            rationale="Tier-1 canonical (regulatory/security/cyber) always requires SME sign-off.",
        )
    return ApprovalRouterOutput(
        route="auto_approve", queue=queue, tier=tier,  # type: ignore[arg-type]
        rationale=f"All guardrails pass; tier-{tier[-1]} domain {queue} auto-approves.",
    )


class ApprovalRouter(Agent):
    name = "ApprovalRouter"
    version = "1.1.0"

    def __init__(self, rules: Optional[RuleRepository] = None):
        self._rules = rules

    def run(self, agent_input: ApprovalRouterInput, ctx: RunContext) -> ApprovalRouterOutput:
        domain_queue = _domain_queue(agent_input.canonical_id)
        tier = _classify_tier(agent_input.canonical_id)

        if self._rules is None:
            out = _legacy_route(agent_input)
            self._emit(ctx, agent_input, out, rule_count=0, fired_rule_id=None)
            return out

        active = self._rules.get_active("approval")
        if not active:
            out = _legacy_route(agent_input)
            self._emit(ctx, agent_input, out, rule_count=0, fired_rule_id=None)
            return out

        context = _flat_context_dict(agent_input)
        fired = apply_rules(active, context, first_match_only=True)
        if not fired:
            # No rule matched even with rules wired — defer to legacy tree.
            out = _legacy_route(agent_input)
            self._emit(ctx, agent_input, out, rule_count=len(active), fired_rule_id=None)
            return out

        fr = fired[0]
        verdict = fr.verdict
        route = verdict.get("route", "sme_queue")
        # Queue precedence: explicit verdict.queue > domain_queue (so a rule
        # can pin "legal" or override the domain map without rewriting the
        # whole approval domain table).
        queue = verdict.get("queue") or domain_queue
        out = ApprovalRouterOutput(
            route=route,  # type: ignore[arg-type]
            queue=queue,
            tier=tier,  # type: ignore[arg-type]
            rationale=verdict.get("rationale", fr.rule.title),
        )
        self._emit(ctx, agent_input, out, rule_count=len(active), fired_rule_id=fr.rule.rule_id)
        return out

    def _emit(
        self,
        ctx: RunContext,
        agent_input: ApprovalRouterInput,
        out: ApprovalRouterOutput,
        *,
        rule_count: int,
        fired_rule_id: Optional[str],
    ) -> None:
        ctx.emit(AgentEvent.make(self.name, self.version, "agent.ApprovalRouter.result", {
            "route": out.route, "queue": out.queue, "tier": out.tier,
            "canonical_id": agent_input.canonical_id,
            "rationale": out.rationale,
            "rule_engine_used": rule_count > 0,
            "active_rule_count": rule_count,
            "fired_rule_id": fired_rule_id,
        }))


def _flat_context_dict(agent_input: ApprovalRouterInput) -> dict:
    return {
        "canonical_id": agent_input.canonical_id,
        "classify_confidence": agent_input.classify_confidence,
        "validate_verdict": agent_input.validate_verdict,
        "pii_halt": agent_input.pii_halt,
        "freshness_stale": agent_input.freshness_stale,
        "consistency_drift": agent_input.consistency_drift,
    }
