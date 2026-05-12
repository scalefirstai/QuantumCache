"""Seed the rule engine with the *current* hardcoded behaviour of
FreshnessAuditor (`services/freshness/agent.py`) and ApprovalRouter
(`services/router/agent.py`).

Idempotent: run twice and you get one rule per ID (upsert). The seeded
rules are tagged `bootstrap`, so the API refuses to delete them without
`?force=true`.

Usage:
    .venv/bin/python -m data.bootstrap.seed_rules
    .venv/bin/python -m data.bootstrap.seed_rules --manifests data/manifests
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.domain.rules import Rule
from infra.adapters.fs_rules import FsRules


def _build_freshness_rules() -> list[Rule]:
    return [
        Rule(
            rule_id="freshness.library.expired",
            engine="freshness",
            title="Library entry expired",
            description=(
                "Flags a library entry as stale when its `expiry_date` is in the past. "
                "Mirrors ddq.md §L04 review_due/expiry_date semantics."
            ),
            priority=10,
            status="active",
            version="1.0.0",
            when={
                "all": [
                    {"field": "library_entry.expiry_date", "op": "exists"},
                    {"field": "library_entry.expiry_date", "op": "age_days_gt", "value": 0},
                ]
            },
            then={
                "stale": True,
                "reason": "library entry expired on {library_entry.expiry_date}",
                "tags": ["library", "expiry"],
            },
            review_queue="ops",
            tags=["bootstrap", "library"],
        ),
        Rule(
            rule_id="freshness.library.review_overdue",
            engine="freshness",
            title="Library entry overdue for review",
            description=(
                "Flags a library entry when its `review_due` date has passed. "
                "Review cadence is governed by SME ownership policy."
            ),
            priority=20,
            status="active",
            version="1.0.0",
            when={
                "all": [
                    {"field": "library_entry.review_due", "op": "exists"},
                    {"field": "library_entry.review_due", "op": "age_days_gt", "value": 0},
                ]
            },
            then={
                "stale": True,
                "reason": "library entry overdue for review since {library_entry.review_due}",
                "tags": ["library", "review"],
            },
            review_queue="ops",
            tags=["bootstrap", "library"],
        ),
        Rule(
            rule_id="freshness.library.bootstrap_tag",
            engine="freshness",
            title="Library entry is bootstrap-tagged",
            description=(
                "Bootstrap-seeded library entries lack SME approval. DATA-PLAN §9 risk #6 "
                "requires SME re-approval before any client packet."
            ),
            priority=30,
            status="active",
            version="1.0.0",
            when={
                "field": "library_entry.tags",
                "op": "contains",
                "value": "bootstrap",
            },
            then={
                "stale": True,
                "reason": "library entry is bootstrap-tagged — needs SME re-approval before client packet",
                "tags": ["library", "bootstrap-guard"],
            },
            review_queue="regulatory",
            tags=["bootstrap", "library"],
        ),
        Rule(
            rule_id="freshness.evidence.pillar3.age_12mo",
            engine="freshness",
            title="Pillar 3 evidence older than 12 months",
            description=(
                "Quarterly Pillar 3 disclosures rotate every quarter; anything older "
                "than 12 months is considered stale for client-facing answers."
            ),
            priority=40,
            status="active",
            version="1.0.0",
            when={
                "any": [
                    {"field": "evidence_oldest.pillar3_date", "op": "exists",
                     "value": None},
                ]
            },
            then={
                "stale": True,
                "reason": "pillar3 evidence older than 12 months: {evidence_oldest.pillar3_date}",
                "tags": ["evidence", "pillar3"],
            },
            review_queue="ops",
            tags=["bootstrap", "evidence"],
        ),
    ]


def _build_approval_rules() -> list[Rule]:
    return [
        Rule(
            rule_id="approval.halt.pii",
            engine="approval",
            title="PII halt → legal review",
            description=(
                "Any PII halt-severity finding requires legal review before any further action. "
                "Mirrors PiiScrubber.halt = True case."
            ),
            priority=10,
            status="active",
            version="1.0.0",
            when={"field": "pii_halt", "op": "truthy"},
            then={
                "route": "halt",
                "queue": "legal",
                "rationale": (
                    "PiiScrubber raised halt — confidentiality risk; legal must review "
                    "before any further action."
                ),
            },
            review_queue="legal",
            tags=["bootstrap", "halt"],
        ),
        Rule(
            rule_id="approval.halt.validate",
            engine="approval",
            title="Validator halt → legal review",
            description=(
                "Validate-verdict = halt means a citation/freshness/scrub guardrail tripped. "
                "Route to legal queue for review."
            ),
            priority=20,
            status="active",
            version="1.0.0",
            when={"field": "validate_verdict", "op": "eq", "value": "halt"},
            then={
                "route": "halt",
                "queue": "legal",
                "rationale": "Validator halted (citation/freshness/scrub guardrail) — legal review.",
            },
            review_queue="legal",
            tags=["bootstrap", "halt"],
        ),
        Rule(
            rule_id="approval.sme.freshness_stale",
            engine="approval",
            title="Freshness stale → SME queue",
            description=(
                "FreshnessAuditor flagged stale evidence or library entry; "
                "domain-routed SME must confirm before send."
            ),
            priority=30,
            status="active",
            version="1.0.0",
            when={"field": "freshness_stale", "op": "truthy"},
            then={
                "route": "sme_queue",
                "rationale": "FreshnessAuditor flagged stale evidence/entry — SME confirmation required.",
            },
            review_queue="ops",
            tags=["bootstrap", "sme"],
        ),
        Rule(
            rule_id="approval.sme.consistency_drift",
            engine="approval",
            title="Consistency drift → SME queue",
            description=(
                "ConsistencyChecker flagged drift versus prior shipped responses. "
                "Avoid sending a contradicting answer without SME blessing."
            ),
            priority=40,
            status="active",
            version="1.0.0",
            when={"field": "consistency_drift", "op": "truthy"},
            then={
                "route": "sme_queue",
                "rationale": (
                    "ConsistencyChecker flagged drift versus prior shipped responses — "
                    "SME confirmation required."
                ),
            },
            review_queue="ops",
            tags=["bootstrap", "sme"],
        ),
        Rule(
            rule_id="approval.sme.low_confidence",
            engine="approval",
            title="Low classify confidence → SME queue",
            description=(
                "QuestionMapper confidence below 0.70 means the canonical mapping is "
                "uncertain. SME must verify before answer is shipped."
            ),
            priority=50,
            status="active",
            version="1.0.0",
            when={"field": "classify_confidence", "op": "lt", "value": 0.70},
            then={
                "route": "sme_queue",
                "rationale": "Classify confidence below 0.70 SME threshold — SME confirmation required.",
            },
            review_queue="ops",
            tags=["bootstrap", "sme"],
        ),
        Rule(
            rule_id="approval.sme.tier1",
            engine="approval",
            title="Tier-1 canonical → SME queue",
            description=(
                "Tier-1 domains (regulatory, infosec, cyber) always require SME sign-off, "
                "even on a clean pass."
            ),
            priority=60,
            status="active",
            version="1.0.0",
            when={
                "any": [
                    {"field": "canonical_id", "op": "startswith", "value": "canon.reg"},
                    {"field": "canonical_id", "op": "startswith", "value": "canon.cyber"},
                    {"field": "canonical_id", "op": "startswith", "value": "canon.is"},
                ]
            },
            then={
                "route": "sme_queue",
                "rationale": "Tier-1 canonical (regulatory/security/cyber) always requires SME sign-off.",
            },
            review_queue="regulatory",
            tags=["bootstrap", "sme", "tier1"],
        ),
        Rule(
            rule_id="approval.auto.clean",
            engine="approval",
            title="Clean pass → auto-approve",
            description=(
                "Default fallthrough: tier-2/3 with no halts, no drift, no low-confidence, "
                "and no freshness issues auto-approves."
            ),
            priority=999,
            status="active",
            version="1.0.0",
            when={},  # vacuously true — matches everything that fell through
            then={
                "route": "auto_approve",
                "rationale": "All guardrails pass; tier-2/3 domain auto-approves.",
            },
            review_queue="ops",
            tags=["bootstrap", "fallthrough"],
        ),
    ]


def seed(manifests_dir: Path, *, dry_run: bool = False) -> int:
    repo = FsRules(manifests_dir)
    rules = _build_freshness_rules() + _build_approval_rules()
    if dry_run:
        for r in rules:
            print(f"  would write {r.rule_id} ({r.engine}, priority={r.priority})")
        return len(rules)
    for r in rules:
        repo.upsert(r)
        print(f"  wrote {r.rule_id} ({r.engine}, status={r.status})")
    return len(rules)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifests", type=Path, default=Path("data/manifests"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    n = seed(args.manifests, dry_run=args.dry_run)
    print(f"\n{'(dry-run) ' if args.dry_run else ''}seeded {n} rules into {args.manifests}/rules/")


if __name__ == "__main__":
    sys.exit(main() or 0)
