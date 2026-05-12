"""
End-to-end engine integration: prove that editing a rule changes the
verdict of the FreshnessAuditor and ApprovalRouter agents.

This is the load-bearing test — without it, the rule engine could be
decorative (the API persists rules, but the agents never read them).

Each test runs against an isolated tmp-dir FS adapter, seeds the
bootstrap rules, runs the agent, then **edits a rule** and re-runs to
assert the verdict changed.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from core.domain.rules import Rule, bump_version
from core.ports.agent import RunContext
from infra.adapters.fs_rules import FsRules
from packages.schemas.agents import (
    ApprovalRouterInput, EvidenceSpan, FreshnessAuditorInput,
)
from services.freshness.agent import FreshnessAuditor
from services.router.agent import ApprovalRouter


def _ctx() -> RunContext:
    return RunContext(
        run_id="test_run",
        taxonomy_version="tx_v0.1",
        library_version="lib_v0.1",
        platform_version="test",
        entity="bny",
    )


def _seed(tmp_path: Path) -> FsRules:
    """Re-seed bootstrap rules into a tmp manifests dir."""
    from data.bootstrap.seed_rules import seed
    seed(tmp_path, dry_run=False)
    return FsRules(tmp_path)


# ════════════════════════════════════════════════════════════════════
# FreshnessAuditor — rule edits change verdict
# ════════════════════════════════════════════════════════════════════

def test_freshness_rule_edit_changes_verdict(tmp_path, capsys):
    repo = _seed(tmp_path)
    agent = FreshnessAuditor(rules=repo)

    # Library entry tagged "bootstrap" — bootstrap rule fires → stale=True.
    inp = FreshnessAuditorInput(
        library_entry={"tags": ["bootstrap", "ops"]},
        evidence_bundle=[],
        today="2026-05-12",
    )
    before = agent.run(inp, _ctx())
    print(f"\n[BEFORE EDIT] stale={before.stale} reasons={before.reasons}")
    assert before.stale is True
    assert any("bootstrap" in r for r in before.reasons)

    # Edit the rule so it requires tag="legacy" instead of "bootstrap".
    # The same input no longer fires the rule.
    r = repo.get("freshness.library.bootstrap_tag")
    assert r is not None
    r.when = {"field": "library_entry.tags", "op": "contains", "value": "legacy"}
    r.version = bump_version(r.version)
    repo.upsert(r)

    after = agent.run(inp, _ctx())
    print(f"[AFTER EDIT]  stale={after.stale} reasons={after.reasons}")

    # The edit makes the bootstrap-tag rule miss; with no library
    # expiry/review fields set and no pillar3 evidence, NO rules should fire.
    assert after.stale is False
    assert after.reasons == []


def test_freshness_new_rule_changes_verdict(tmp_path, capsys):
    """Add a brand-new active rule; verdict flips for an input that
    previously cleared every existing rule."""
    repo = _seed(tmp_path)
    agent = FreshnessAuditor(rules=repo)

    inp = FreshnessAuditorInput(
        library_entry={"id": "lib_x", "tags": ["confidential"]},
        evidence_bundle=[],
        today="2026-05-12",
    )
    before = agent.run(inp, _ctx())
    print(f"\n[BEFORE NEW RULE] stale={before.stale} reasons={before.reasons}")
    assert before.stale is False

    # New rule: any entry tagged "confidential" is stale until SME review.
    new_rule = Rule(
        rule_id="custom.confidential_gate",
        engine="freshness",
        title="Confidential gate",
        description="Confidential tag = client packet gate",
        priority=15,
        status="active",
        version="1.0.0",
        when={"field": "library_entry.tags", "op": "contains", "value": "confidential"},
        then={"stale": True, "reason": "confidential entry {library_entry.id} requires SME review"},
        review_queue="legal",
        tags=["test"],
    )
    repo.upsert(new_rule)

    after = agent.run(inp, _ctx())
    print(f"[AFTER NEW RULE]  stale={after.stale} reasons={after.reasons}")
    assert after.stale is True
    assert any("lib_x" in r for r in after.reasons)


# ════════════════════════════════════════════════════════════════════
# ApprovalRouter — rule edits change verdict
# ════════════════════════════════════════════════════════════════════

def test_approval_lower_confidence_threshold(tmp_path, capsys):
    """Edit the classify-confidence rule from <0.70 to <0.95.
    An input at confidence=0.80 now routes to SME instead of auto-approve."""
    repo = _seed(tmp_path)
    agent = ApprovalRouter(rules=repo)

    inp = ApprovalRouterInput(
        canonical_id="canon.subc.bcp",  # tier-2 (not in TIER1_PREFIXES)
        classify_confidence=0.80,
        validate_verdict="pass",
        pii_halt=False,
        freshness_stale=False,
        consistency_drift=False,
    )
    before = agent.run(inp, _ctx())
    print(f"\n[BEFORE THRESHOLD EDIT] route={before.route} queue={before.queue} rationale={before.rationale[:80]}")
    assert before.route == "auto_approve"

    # Tighten the threshold.
    r = repo.get("approval.sme.low_confidence")
    assert r is not None
    r.when = {"field": "classify_confidence", "op": "lt", "value": 0.95}
    r.version = bump_version(r.version)
    repo.upsert(r)

    after = agent.run(inp, _ctx())
    print(f"[AFTER THRESHOLD EDIT]  route={after.route} queue={after.queue} rationale={after.rationale[:80]}")
    assert after.route == "sme_queue"
    assert "below 0.70" not in after.rationale or "SME" in after.rationale  # rule fired


def test_approval_inactive_rule_does_not_fire(tmp_path, capsys):
    """Mark the PII-halt rule as `archived`; even a PII-halt input no
    longer routes to legal under the rule engine path."""
    repo = _seed(tmp_path)
    agent = ApprovalRouter(rules=repo)

    inp = ApprovalRouterInput(
        canonical_id="canon.subc.bcp",
        classify_confidence=0.95,
        validate_verdict="pass",
        pii_halt=True,
        freshness_stale=False,
        consistency_drift=False,
    )
    before = agent.run(inp, _ctx())
    print(f"\n[BEFORE ARCHIVE] route={before.route} queue={before.queue}")
    assert before.route == "halt"
    assert before.queue == "legal"

    # Archive the PII rule.
    r = repo.get("approval.halt.pii")
    assert r is not None
    r.status = "archived"
    repo.upsert(r)

    after = agent.run(inp, _ctx())
    print(f"[AFTER ARCHIVE]  route={after.route} queue={after.queue} rationale={after.rationale[:80]}")
    # No rule fires for pii_halt now; the next-priority rule that *does*
    # fire is approval.auto.clean (the fallthrough). Queue stays as the
    # domain-mapped queue for canon.subc → "ops".
    assert after.route == "auto_approve"
    assert after.queue == "ops"


# ════════════════════════════════════════════════════════════════════
# Event journal — emitted events carry rule-engine metadata
# ════════════════════════════════════════════════════════════════════

def test_freshness_emits_rule_engine_event(tmp_path):
    repo = _seed(tmp_path)
    agent = FreshnessAuditor(rules=repo)
    ctx = _ctx()
    agent.run(FreshnessAuditorInput(
        library_entry={"tags": ["bootstrap"]},
        evidence_bundle=[],
        today="2026-05-12",
    ), ctx)
    events = [e for e in ctx.events if e.kind == "agent.FreshnessAuditor.result"]
    assert len(events) == 1
    payload = events[0].payload
    assert payload["rule_engine_used"] is True
    assert payload["active_rule_count"] >= 4
    assert "freshness.library.bootstrap_tag" in payload["fired_rule_ids"]


def test_approval_emits_fired_rule_id(tmp_path):
    repo = _seed(tmp_path)
    agent = ApprovalRouter(rules=repo)
    ctx = _ctx()
    agent.run(ApprovalRouterInput(
        canonical_id="canon.is.iam",
        classify_confidence=0.95,
        validate_verdict="pass",
        pii_halt=True,
        freshness_stale=False,
        consistency_drift=False,
    ), ctx)
    events = [e for e in ctx.events if e.kind == "agent.ApprovalRouter.result"]
    assert len(events) == 1
    payload = events[0].payload
    assert payload["rule_engine_used"] is True
    assert payload["fired_rule_id"] == "approval.halt.pii"


# ════════════════════════════════════════════════════════════════════
# Legacy fallthrough — agent without rules behaves identically to v1.0.0
# ════════════════════════════════════════════════════════════════════

def test_freshness_legacy_path_still_works():
    """No rules injected → hardcoded thresholds still produce the right
    answer. This is the safety net for callers that haven't migrated."""
    agent = FreshnessAuditor(rules=None)
    out = agent.run(FreshnessAuditorInput(
        library_entry={"tags": ["bootstrap"]},
        evidence_bundle=[],
        today="2026-05-12",
    ), _ctx())
    assert out.stale is True
    assert any("bootstrap" in r for r in out.reasons)


def test_approval_legacy_path_still_works():
    agent = ApprovalRouter(rules=None)
    out = agent.run(ApprovalRouterInput(
        canonical_id="canon.is.iam",
        classify_confidence=0.95,
        validate_verdict="pass",
        pii_halt=True,
        freshness_stale=False,
        consistency_drift=False,
    ), _ctx())
    assert out.route == "halt"
    assert out.queue == "legal"
