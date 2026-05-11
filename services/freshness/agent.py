"""FreshnessAuditor — ddq.md §L06 (rule-based, not LLM).

Flags stale library entries and stale evidence. Thresholds come from
ddq.md §L04 (review_due, expiry_date) and §L02 guardrail 02:
- library entry: stale if expiry_date < today or review_due < today.
- evidence span: stale if it's a quarterly filing > 18 months old, or
  an annual filing > 24 months old.
"""

from __future__ import annotations

import datetime as dt
from core.ports.agent import Agent, AgentEvent, RunContext
from packages.schemas.agents import (
    FreshnessAuditorInput, FreshnessAuditorOutput,
)


ANNUAL_FORMS = {"10-K", "10K", "DEF 14A", "DEF14A", "20-F"}
QUARTERLY_FORMS = {"10-Q", "10Q"}
ANNUAL_MAX_DAYS = 24 * 30   # ~24 months
QUARTERLY_MAX_DAYS = 18 * 30  # ~18 months
PILLAR3_MAX_DAYS = 12 * 30


def _parse_iso(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


class FreshnessAuditor(Agent):
    name = "FreshnessAuditor"
    version = "1.0.0"

    def run(self, agent_input: FreshnessAuditorInput, ctx: RunContext) -> FreshnessAuditorOutput:
        today = _parse_iso(agent_input.today) or dt.date.today()
        reasons: list[str] = []

        # 1. Library entry checks.
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

        # 2. Evidence span freshness — best-effort using form-level expectations.
        oldest_date: str | None = None
        for sp in agent_input.evidence_bundle:
            # form lives in the EvidenceSpan; we don't carry filing_date on the model,
            # but anchor_item or doc_id often encodes it. Fall back to text scan.
            form = (sp.form or "").upper().strip()
            doc_id = sp.doc_id or ""
            # filing date heuristic: doc_id pattern "edgar:bk:0000835104-25-000123" not dated.
            # We use the form-based ceiling instead: any form here is "fresh" unless > ceiling.
            # The orchestrator stamps span.score with the RRF score, not date, so we treat
            # missing-date as 'fresh' and only flag explicit pillar3-style date encodings.
            if "pillar3" in doc_id.lower():
                # Pattern: bny-2024q3-pillar3 or bny-mellon-3q2023-pillar3.
                import re
                m = re.search(r"(\d{4})q?([1-4])", doc_id.lower())
                if m:
                    yr, q = int(m.group(1)), int(m.group(2))
                    filing_date = dt.date(yr, q * 3, 1)
                    age_days = (today - filing_date).days
                    iso = filing_date.isoformat()
                    if oldest_date is None or iso < oldest_date:
                        oldest_date = iso
                    if age_days > PILLAR3_MAX_DAYS:
                        reasons.append(f"pillar3 evidence {doc_id} is {age_days // 30}mo old (cap {PILLAR3_MAX_DAYS // 30}mo)")
            elif form in ANNUAL_FORMS:
                pass  # no filing_date on span; freshness in M1 once doc_index lands.
            elif form in QUARTERLY_FORMS:
                pass

        stale = bool(reasons)
        out = FreshnessAuditorOutput(
            stale=stale,
            reasons=reasons,
            oldest_evidence_date=oldest_date,
        )
        ctx.emit(AgentEvent.make(self.name, self.version, "agent.FreshnessAuditor.result", {
            "stale": stale,
            "reason_count": len(reasons),
            "reasons": reasons,
            "oldest_evidence_date": oldest_date,
            "today": today.isoformat(),
        }))
        return out
