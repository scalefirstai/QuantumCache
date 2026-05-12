"""FreshnessAuditor — ddq.md §L06 (rule-based, not LLM).

With a `RuleRepository` injected, the agent evaluates *only* the rules in
the engine (no hardcoded thresholds). Without one, it falls back to the
legacy hardcoded behaviour so existing test fixtures keep working.

Rules are configured via `/api/v1/rules` (engine="freshness"). See
`docs/specs/rule-engine.md` for the DSL.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Optional

from core.domain.rules import Rule, apply_rules
from core.ports.agent import Agent, AgentEvent, RunContext
from core.ports.rules import RuleRepository
from packages.schemas.agents import (
    FreshnessAuditorInput, FreshnessAuditorOutput,
)


# ── Legacy hardcoded constants (fallthrough when no rule engine is wired) ──
ANNUAL_FORMS = {"10-K", "10K", "DEF 14A", "DEF14A", "20-F"}
QUARTERLY_FORMS = {"10-Q", "10Q"}
ANNUAL_MAX_DAYS = 24 * 30   # ~24 months
QUARTERLY_MAX_DAYS = 18 * 30  # ~18 months
PILLAR3_MAX_DAYS = 12 * 30


def _parse_iso(s: Optional[str]) -> Optional[dt.date]:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _pillar3_date_from_doc_id(doc_id: str) -> Optional[dt.date]:
    """Extract a `YYYYqQ`-style filing date from the doc_id. Returns None
    if no quarter token is present."""
    if "pillar3" not in doc_id.lower():
        return None
    m = re.search(r"(\d{4})q?([1-4])", doc_id.lower())
    if not m:
        return None
    return dt.date(int(m.group(1)), int(m.group(2)) * 3, 1)


def _build_context(agent_input: FreshnessAuditorInput, today: dt.date) -> dict:
    """Flatten the agent input into a dotted-path-addressable dict for the
    rule DSL. `evidence_oldest.pillar3_date` is a pre-computed convenience
    field — the DSL can't iterate lists today, so we surface aggregates here.
    """
    pillar3_dates: list[dt.date] = []
    for sp in agent_input.evidence_bundle:
        d = _pillar3_date_from_doc_id(sp.doc_id or "")
        if d is not None:
            pillar3_dates.append(d)
    oldest_pillar3 = min(pillar3_dates) if pillar3_dates else None
    is_pillar3_stale = (
        oldest_pillar3 is not None
        and (today - oldest_pillar3).days > PILLAR3_MAX_DAYS
    )
    return {
        "library_entry": agent_input.library_entry or {},
        "evidence": [sp.model_dump() for sp in agent_input.evidence_bundle],
        "evidence_oldest": {
            # surfaced only when stale, so the rule's exists-check fires
            "pillar3_date": oldest_pillar3.isoformat() if is_pillar3_stale else None,
        },
        "today": today.isoformat(),
    }


def _legacy_freshness(agent_input: FreshnessAuditorInput, today: dt.date) -> FreshnessAuditorOutput:
    """The pre-rule-engine logic. Kept so legacy callers (no `rules=`) don't
    silently change behaviour."""
    reasons: list[str] = []

    if agent_input.library_entry:
        le = agent_input.library_entry
        exp = _parse_iso(le.get("expiry_date"))
        review = _parse_iso(le.get("review_due"))
        if exp and exp < today:
            reasons.append(f"library entry expired on {exp.isoformat()}")
        if review and review < today:
            reasons.append(f"library entry overdue for review since {review.isoformat()}")
        if "bootstrap" in (le.get("tags") or []):
            reasons.append("library entry is bootstrap-tagged — needs SME re-approval before client packet")

    oldest_date: Optional[str] = None
    for sp in agent_input.evidence_bundle:
        d = _pillar3_date_from_doc_id(sp.doc_id or "")
        if d is None:
            continue
        iso = d.isoformat()
        if oldest_date is None or iso < oldest_date:
            oldest_date = iso
        age_days = (today - d).days
        if age_days > PILLAR3_MAX_DAYS:
            reasons.append(f"pillar3 evidence {sp.doc_id} is {age_days // 30}mo old (cap {PILLAR3_MAX_DAYS // 30}mo)")

    return FreshnessAuditorOutput(
        stale=bool(reasons),
        reasons=reasons,
        oldest_evidence_date=oldest_date,
    )


class FreshnessAuditor(Agent):
    name = "FreshnessAuditor"
    version = "1.1.0"

    def __init__(self, rules: Optional[RuleRepository] = None):
        self._rules = rules

    def run(self, agent_input: FreshnessAuditorInput, ctx: RunContext) -> FreshnessAuditorOutput:
        today = _parse_iso(agent_input.today) or dt.date.today()

        if self._rules is None:
            out = _legacy_freshness(agent_input, today)
            self._emit(ctx, out, today, rule_count=0, fired_rule_ids=[])
            return out

        active = self._rules.get_active("freshness")
        context = _build_context(agent_input, today)
        fired = apply_rules(active, context, today=today, first_match_only=False)
        reasons = [fr.verdict.get("reason", fr.rule.title) for fr in fired]
        stale = any(bool(fr.verdict.get("stale", True)) for fr in fired)

        # Oldest pillar3 date is still useful telemetry even when no rule cited it.
        pillar3_dates: list[str] = []
        for sp in agent_input.evidence_bundle:
            d = _pillar3_date_from_doc_id(sp.doc_id or "")
            if d:
                pillar3_dates.append(d.isoformat())
        oldest = min(pillar3_dates) if pillar3_dates else None

        out = FreshnessAuditorOutput(
            stale=stale,
            reasons=reasons,
            oldest_evidence_date=oldest,
        )
        self._emit(ctx, out, today, rule_count=len(active), fired_rule_ids=[fr.rule.rule_id for fr in fired])
        return out

    def _emit(
        self,
        ctx: RunContext,
        out: FreshnessAuditorOutput,
        today: dt.date,
        *,
        rule_count: int,
        fired_rule_ids: list[str],
    ) -> None:
        ctx.emit(AgentEvent.make(self.name, self.version, "agent.FreshnessAuditor.result", {
            "stale": out.stale,
            "reason_count": len(out.reasons),
            "reasons": out.reasons,
            "oldest_evidence_date": out.oldest_evidence_date,
            "today": today.isoformat(),
            "rule_engine_used": rule_count > 0,
            "active_rule_count": rule_count,
            "fired_rule_ids": fired_rule_ids,
        }))
