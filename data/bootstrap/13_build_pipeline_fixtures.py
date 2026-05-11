#!/usr/bin/env python3
"""Build a UI fixture that visualizes the email → 8-agent → sealed-DDQ flow.

Reads the latest aggregated DDQ packet from `data/manifests/inbox/` plus the
matching per-question sealed runs from `data/manifests/runs/`, and produces:

    apps/ui/src/mocks/fixtures/pipelines/<ddq_id>.json
    apps/ui/src/mocks/fixtures/pipelines-index.json

The UI's /pipeline/$ddqId route consumes this directly — no extra
transformation in the frontend.

Usage:
    .venv/bin/python data/bootstrap/13_build_pipeline_fixtures.py
    .venv/bin/python data/bootstrap/13_build_pipeline_fixtures.py --ddq-id ddq_8db64d9cb6c5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

INBOX_DIR = REPO_ROOT / "data" / "manifests" / "inbox"
RUNS_DIR = REPO_ROOT / "data" / "manifests" / "runs"
EML_DIR = REPO_ROOT / "data" / "fixtures" / "inbox"

UI_FIXTURES = REPO_ROOT / "apps" / "ui" / "src" / "mocks" / "fixtures"
PIPELINES_DIR = UI_FIXTURES / "pipelines"
INDEX_PATH = UI_FIXTURES / "pipelines-index.json"


# Stage definition — derived from ddq.md §L06 + L07. Keep in sync with the
# `STAGE_DEFS` constant in apps/ui/src/types/pipeline.ts.
PIPELINE_STAGES = [
    {"id": "intake",       "title": "Email intake",       "agent": "EmailParser",       "kind": "system"},
    {"id": "mapper",       "title": "QuestionMapper",     "agent": "QuestionMapper",    "kind": "agent"},
    {"id": "library",      "title": "Library lookup",     "agent": "LibraryService",    "kind": "system"},
    {"id": "retrieve",     "title": "Retrieve",           "agent": "Retrieval",         "kind": "system"},
    {"id": "sourcer",      "title": "EvidenceSourcer",    "agent": "EvidenceSourcer",   "kind": "agent"},
    {"id": "drafter",      "title": "DraftComposer",      "agent": "DraftComposer",     "kind": "agent"},
    {"id": "verifier",     "title": "CitationVerifier",   "agent": "CitationVerifier",  "kind": "agent"},
    {"id": "consistency",  "title": "ConsistencyChecker", "agent": "ConsistencyChecker","kind": "agent"},
    {"id": "pii",          "title": "PiiScrubber",        "agent": "PiiScrubber",       "kind": "agent"},
    {"id": "freshness",    "title": "FreshnessAuditor",   "agent": "FreshnessAuditor",  "kind": "rule"},
    {"id": "router",       "title": "ApprovalRouter",     "agent": "ApprovalRouter",    "kind": "rule"},
    {"id": "sealed",       "title": "Seal (L01)",         "agent": "AuditJournal",     "kind": "system"},
]


# Maps an event in the sealed journal to one of our pipeline stages.
EVENT_KIND_TO_STAGE = {
    "intake.received":             "intake",
    "agent.QuestionMapper.invoke": "mapper",
    "agent.QuestionMapper.result": "mapper",
    "library.lookup":              "library",
    "retrieve.hybrid":             "retrieve",
    "retrieve.query":              "retrieve",
    "retrieve.result":             "retrieve",
    "agent.EvidenceSourcer.invoke":  "sourcer",
    "agent.EvidenceSourcer.result":  "sourcer",
    "agent.DraftComposer.invoke":    "drafter",
    "agent.DraftComposer.result":    "drafter",
    "agent.DraftComposer.skip":      "drafter",
    "agent.CitationVerifier.invoke": "verifier",
    "agent.CitationVerifier.result": "verifier",
    "agent.ConsistencyChecker.invoke": "consistency",
    "agent.ConsistencyChecker.result": "consistency",
    "agent.PiiScrubber.invoke":      "pii",
    "agent.PiiScrubber.result":      "pii",
    "agent.FreshnessAuditor.result": "freshness",
    "agent.ApprovalRouter.result":   "router",
    "validate.aggregate":            "router",
}


def _short_hash(h: str | None, n: int = 12) -> str:
    if not h:
        return "—"
    return h.split(":", 1)[-1][:n]


def _stage_status(stage_id: str, sealed_run: dict) -> str:
    """pass | warn | halt | skip — drives the UI badge colour."""
    agents = sealed_run.get("agents") or {}
    verdict = sealed_run.get("verdict")
    route = sealed_run.get("route")
    if stage_id == "intake":
        return "pass"
    if stage_id == "mapper":
        m = agents.get("QuestionMapper") or {}
        return "warn" if m.get("routed_to_sme") else "pass"
    if stage_id == "library":
        return "pass"  # informational
    if stage_id == "retrieve":
        return "pass"
    if stage_id == "sourcer":
        s = agents.get("EvidenceSourcer") or {}
        return "pass" if s.get("sufficient") else "warn"
    if stage_id == "drafter":
        d = agents.get("DraftComposer") or {}
        return "skip" if not d.get("draft_chars") else "pass"
    if stage_id == "verifier":
        v = agents.get("CitationVerifier") or {}
        if not v.get("checked"):
            return "skip"
        return "pass" if v.get("all_pass") else "halt"
    if stage_id == "consistency":
        c = agents.get("ConsistencyChecker") or {}
        return "warn" if c.get("drift") else "pass"
    if stage_id == "pii":
        p = agents.get("PiiScrubber") or {}
        return "halt" if p.get("halt") else "pass"
    if stage_id == "freshness":
        f = agents.get("FreshnessAuditor") or {}
        return "warn" if f.get("stale") else "pass"
    if stage_id == "router":
        if route == "halt":
            return "halt"
        if route == "sme_queue":
            return "warn"
        return "pass"
    if stage_id == "sealed":
        return "halt" if verdict == "halt" else "pass"
    return "pass"


def _stage_summary(stage_id: str, sealed_run: dict) -> str:
    """One-line human label shown on the pipeline strip."""
    agents = sealed_run.get("agents") or {}
    if stage_id == "intake":
        return f"Q{sealed_run.get('input', {}).get('question_id', '?')} · {sealed_run.get('input', {}).get('framework', '?')}"
    if stage_id == "mapper":
        m = agents.get("QuestionMapper") or {}
        cid = m.get("canonical_id") or "unclassified"
        return f"{cid} · conf {m.get('confidence', 0):.2f}"
    if stage_id == "library":
        # We rely on the library.lookup event payload — checked at build time.
        for e in sealed_run.get("events", []):
            if e.get("kind") == "library.lookup":
                hit = e.get("payload", {}).get("hit")
                return "library hit" if hit else "library miss"
        return "library lookup"
    if stage_id == "retrieve":
        for e in sealed_run.get("events", []):
            if e.get("kind") == "retrieve.hybrid":
                p = e.get("payload", {})
                return f"hybrid · {p.get('returned', 0)} spans · top {p.get('top_score', 0):.4f}"
        return "hybrid retrieval"
    if stage_id == "sourcer":
        s = agents.get("EvidenceSourcer") or {}
        return f"{s.get('selected', 0)} selected · {'sufficient' if s.get('sufficient') else 'insufficient'}"
    if stage_id == "drafter":
        d = agents.get("DraftComposer") or {}
        if not d.get("draft_chars"):
            return "skipped (no evidence)"
        return f"{d.get('tier', '?')} · {d.get('draft_chars', 0)} chars · {d.get('citation_count', 0)} citations"
    if stage_id == "verifier":
        v = agents.get("CitationVerifier") or {}
        if not v.get("checked"):
            return "no citations to verify"
        return f"{v.get('checked', 0)} citations · {'all pass' if v.get('all_pass') else 'unsupported'}"
    if stage_id == "consistency":
        c = agents.get("ConsistencyChecker") or {}
        return "drift detected" if c.get("drift") else "consistent"
    if stage_id == "pii":
        p = agents.get("PiiScrubber") or {}
        return f"{p.get('findings', 0)} findings · {'halt' if p.get('halt') else 'clean'}"
    if stage_id == "freshness":
        f = agents.get("FreshnessAuditor") or {}
        if f.get("stale"):
            return f"stale · {len(f.get('reasons') or [])} reason(s)"
        return "fresh"
    if stage_id == "router":
        r = agents.get("ApprovalRouter") or {}
        q = r.get("queue") or "?"
        return f"{r.get('route', '?')} → {q} (tier {r.get('tier', '?')})"
    if stage_id == "sealed":
        return f"merkle {_short_hash(sealed_run.get('merkle_root'))}"
    return ""


def _events_for_stage(stage_id: str, sealed_run: dict) -> list[dict]:
    """Pull the raw journal events that belong to this stage."""
    out = []
    for e in sealed_run.get("events", []):
        if EVENT_KIND_TO_STAGE.get(e.get("kind")) == stage_id:
            out.append({
                "eventId":   e.get("event_id"),
                "ts":        e.get("ts"),
                "kind":      e.get("kind"),
                "agent":     e.get("agent"),
                "payload":   e.get("payload") or {},
                "payloadHash": e.get("payload_hash"),
                "chainHash":   e.get("chain_hash"),
            })
    return out


def _stage_payload(stage_id: str, sealed_run: dict) -> dict:
    """Stage-specific structured payload for the data inspector."""
    agents = sealed_run.get("agents") or {}
    events = sealed_run.get("events") or []

    def first_event_payload(kind: str) -> dict:
        for e in events:
            if e.get("kind") == kind:
                return e.get("payload") or {}
        return {}

    if stage_id == "intake":
        return {
            "question":   sealed_run.get("input"),
            "platformVersion": sealed_run.get("platform_version"),
            "taxonomyVersion": sealed_run.get("taxonomy_version"),
            "libraryVersion":  sealed_run.get("library_version"),
        }
    if stage_id == "mapper":
        invoke = first_event_payload("agent.QuestionMapper.invoke")
        result = first_event_payload("agent.QuestionMapper.result")
        return {
            "input": {
                "framework": invoke.get("framework"),
                "candidateCount": invoke.get("candidate_count"),
                "promptHash": invoke.get("prompt_hash"),
                "modelTier": invoke.get("model_tier"),
            },
            "output": {
                "canonicalId": result.get("canonical_id"),
                "confidence": result.get("confidence"),
                "routedToSme": result.get("routed_to_sme"),
            },
            "tokens": result.get("tokens"),
            "agentSummary": agents.get("QuestionMapper"),
        }
    if stage_id == "library":
        p = first_event_payload("library.lookup")
        return {
            "canonicalId": p.get("canonical_id"),
            "entity": p.get("entity"),
            "product": p.get("product"),
            "hit": p.get("hit"),
            "entryId": p.get("entry_id"),
        }
    if stage_id == "retrieve":
        p = first_event_payload("retrieve.hybrid")
        return {
            "filters": p.get("filters"),
            "k": p.get("k"),
            "returned": p.get("returned"),
            "topScore": p.get("top_score"),
            "topSources": p.get("top_3_sources"),
        }
    if stage_id == "sourcer":
        invoke = first_event_payload("agent.EvidenceSourcer.invoke")
        result = first_event_payload("agent.EvidenceSourcer.result")
        return {
            "input": {
                "candidateCount": invoke.get("candidate_count"),
                "libraryHit": invoke.get("library_hit"),
                "promptHash": invoke.get("prompt_hash"),
            },
            "output": {
                "selectedSpanIds": result.get("selected_span_ids"),
                "selectedCount": result.get("selected_count"),
                "sufficient": result.get("sufficient"),
            },
            "tokens": result.get("tokens"),
        }
    if stage_id == "drafter":
        invoke = first_event_payload("agent.DraftComposer.invoke")
        result = first_event_payload("agent.DraftComposer.result")
        skip = first_event_payload("agent.DraftComposer.skip")
        return {
            "input": {
                "tier": invoke.get("tier"),
                "evidenceCount": invoke.get("evidence_count"),
                "usedLibraryEntry": invoke.get("used_library_entry"),
                "promptHash": invoke.get("prompt_hash"),
            },
            "output": {
                "draftChars": result.get("draft_chars"),
                "citationCount": result.get("citation_count"),
                "citedSpanIds": result.get("cited_span_ids"),
                "tierUsed": result.get("tier_used"),
            },
            "draftText": sealed_run.get("outbound_response"),
            "evidenceRefs": sealed_run.get("evidence_refs"),
            "tokens": result.get("tokens"),
            "skip": skip or None,
        }
    if stage_id == "verifier":
        invoke = first_event_payload("agent.CitationVerifier.invoke")
        result = first_event_payload("agent.CitationVerifier.result")
        return {
            "input": {
                "citationCount": invoke.get("citation_count"),
                "unresolvedCount": invoke.get("unresolved_count"),
                "promptHash": invoke.get("prompt_hash"),
            },
            "output": {
                "allPass": result.get("all_pass"),
                "checked": result.get("checked"),
                "unresolved": result.get("unresolved"),
                "unsupported": result.get("unsupported"),
            },
            "tokens": result.get("tokens"),
        }
    if stage_id == "consistency":
        invoke = first_event_payload("agent.ConsistencyChecker.invoke")
        result = first_event_payload("agent.ConsistencyChecker.result")
        return {
            "input": {
                "priorCount": invoke.get("prior_count") or 0,
                "promptHash": invoke.get("prompt_hash"),
            },
            "output": {
                "consistent": result.get("consistent"),
                "driftDetected": result.get("drift_detected"),
                "reason": result.get("reason"),
            },
            "tokens": result.get("tokens"),
        }
    if stage_id == "pii":
        invoke = first_event_payload("agent.PiiScrubber.invoke")
        result = first_event_payload("agent.PiiScrubber.result")
        return {
            "input": {
                "regexFindings": invoke.get("regex_findings"),
                "inputChars": invoke.get("input_chars"),
            },
            "output": {
                "findingsTotal": result.get("findings_total"),
                "llmFindings": result.get("llm_findings"),
                "halt": result.get("halt"),
            },
            "tokens": result.get("tokens"),
        }
    if stage_id == "freshness":
        p = first_event_payload("agent.FreshnessAuditor.result")
        return {
            "stale": p.get("stale"),
            "reasons": p.get("reasons"),
            "oldestEvidenceDate": p.get("oldest_evidence_date"),
            "today": p.get("today"),
        }
    if stage_id == "router":
        agg = first_event_payload("validate.aggregate")
        rt = first_event_payload("agent.ApprovalRouter.result")
        return {
            "aggregate": agg,
            "route": rt.get("route"),
            "queue": rt.get("queue"),
            "tier": rt.get("tier"),
            "rationale": rt.get("rationale"),
            "canonicalId": rt.get("canonical_id"),
        }
    if stage_id == "sealed":
        return {
            "merkleRoot": sealed_run.get("merkle_root"),
            "outboundResponseHash": sealed_run.get("outbound_response_hash"),
            "evidenceRefs": sealed_run.get("evidence_refs"),
            "verdict": sealed_run.get("verdict"),
            "route": sealed_run.get("route"),
            "sealedAt": sealed_run.get("sealed_at"),
            "outboundResponse": sealed_run.get("outbound_response"),
        }
    return {}


def _build_question(q_result: dict, sealed_run: dict) -> dict:
    stages = []
    for s in PIPELINE_STAGES:
        stages.append({
            "id":       s["id"],
            "title":    s["title"],
            "agent":    s["agent"],
            "kind":     s["kind"],
            "status":   _stage_status(s["id"], sealed_run),
            "summary":  _stage_summary(s["id"], sealed_run),
            "events":   _events_for_stage(s["id"], sealed_run),
            "payload":  _stage_payload(s["id"], sealed_run),
        })
    return {
        "questionId":   q_result["question_id"],
        "framework":    q_result["framework"],
        "text":         sealed_run.get("input", {}).get("text"),
        "runId":        q_result["run_id"],
        "canonicalId":  q_result.get("canonical_id"),
        "confidence":   q_result.get("confidence"),
        "libraryHit":   q_result.get("library_hit"),
        "verdict":      q_result.get("validate_verdict"),
        "route":        q_result.get("route"),
        "queue":        q_result.get("queue"),
        "tier":         q_result.get("tier"),
        "elapsedMs":    q_result.get("elapsed_ms"),
        "draftChars":   q_result.get("draft_chars"),
        "citationCount": q_result.get("citation_count"),
        "merkleRoot":   q_result.get("merkle_root"),
        "outboundPreview": q_result.get("outbound_preview"),
        "stages": stages,
    }


def build_pipeline(ddq_id: str) -> dict:
    inbox_path = INBOX_DIR / f"{ddq_id}.json"
    if not inbox_path.exists():
        raise FileNotFoundError(f"No inbox manifest at {inbox_path}")
    packet = json.loads(inbox_path.read_text(encoding="utf-8"))

    # Email body (best-effort — read the source .eml subject+attachments,
    # we already have most of what we need on the packet).
    questions = []
    for q in packet["results"]:
        run_id = q.get("run_id")
        if not run_id:
            continue
        run_path = RUNS_DIR / f"{run_id}.json"
        if not run_path.exists():
            continue
        sealed = json.loads(run_path.read_text(encoding="utf-8"))
        questions.append(_build_question(q, sealed))

    return {
        "ddqId":      packet["ddq_id"],
        "subject":    packet.get("subject"),
        "from":       packet.get("from"),
        "to":         packet.get("to"),
        "rawEmlSha256": packet.get("raw_eml_sha256"),
        "sealedAt":   packet.get("sealed_at"),
        "platformVersion": packet.get("platform_version"),
        "questionCount":   packet.get("question_count"),
        "questions":  questions,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--ddq-id", help="Specific ddq_id (default: latest sealed)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    PIPELINES_DIR.mkdir(parents=True, exist_ok=True)

    inbox_files = sorted(INBOX_DIR.glob("ddq_*.json"))
    if not inbox_files:
        print(f"No inbox manifests in {INBOX_DIR}", file=sys.stderr)
        return 2

    if args.ddq_id:
        targets = [INBOX_DIR / f"{args.ddq_id}.json"]
    else:
        # Build every DDQ packet that has a manifest.
        targets = inbox_files

    index = []
    for path in targets:
        if not path.exists():
            print(f"warn: missing {path}", file=sys.stderr)
            continue
        ddq_id = path.stem
        pipeline = build_pipeline(ddq_id)
        out = PIPELINES_DIR / f"{ddq_id}.json"
        out.write_text(json.dumps(pipeline, indent=2, default=str), encoding="utf-8")
        print(f"wrote {out.relative_to(REPO_ROOT)}  "
              f"({len(pipeline['questions'])} questions, "
              f"{sum(len(q['stages']) for q in pipeline['questions'])} stages total)")
        index.append({
            "ddqId":        pipeline["ddqId"],
            "subject":      pipeline["subject"],
            "from":         pipeline["from"],
            "questionCount": pipeline["questionCount"],
            "sealedAt":     pipeline["sealedAt"],
        })

    INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"wrote {INDEX_PATH.relative_to(REPO_ROOT)}  ({len(index)} pipelines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
