#!/usr/bin/env python3
"""End-to-end DDQ orchestrator — ddq.md §L07.

Wires an inbound email through the 8-agent roster (§L06) against the live
local backends populated by Days 1–10:

    Email (.eml)
        └─► intake.email_parser
              └─► per question, run the L07 graph:
                      classify (QuestionMapper)
                          └─► library_lookup
                                 ├─hit─► (use library text)
                                 └─miss► retrieve_evidence
                                            └─► EvidenceSourcer
                                                  └─► DraftComposer
                                                        └─► CitationVerifier
                                                              └─► ConsistencyChecker
                                                                    └─► PiiScrubber
                                                                          └─► FreshnessAuditor
                                                                                └─► ApprovalRouter
                                                                                      └─► seal_response (L01)

Each question produces a hash-chained event journal, sealed to S3 (LocalStack)
under bucket `bny-ddq-runs-sealed/<run_id>/sealed.json`. The whole DDQ also
gets aggregated under `inbox/<ddq_id>/sealed_packet.json`.

Usage:
    .venv/bin/python -m apps.orchestrator.main \
        --eml data/fixtures/inbox/sample_ddq_2026q2.eml
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from data.bootstrap._lib import MANIFESTS_DIR, s3_client                # noqa: E402

from core.domain.library import LibraryKey                              # noqa: E402
from core.ports.agent import AgentEvent, RunContext                     # noqa: E402
from infra.adapters.mongo_library import MongoLibrary                   # noqa: E402
from infra.adapters.mongo_taxonomy import MongoTaxonomy                 # noqa: E402

from packages.llm_sdk import AnthropicClient                            # noqa: E402
from packages.schemas.agents import (                                   # noqa: E402
    ApprovalRouterInput, CitationVerifierInput,
    ConsistencyCheckerInput, DraftComposerInput, EvidenceSourcerInput,
    EvidenceSpan, FreshnessAuditorInput, PiiScrubberInput,
    QuestionMapperInput,
)

from services.classifier.agent import QuestionMapper                    # noqa: E402
from services.consistency.agent import ConsistencyChecker               # noqa: E402
from services.drafter.agent import DraftComposer                        # noqa: E402
from services.freshness.agent import FreshnessAuditor                   # noqa: E402
from services.intake.email_parser import IngestedDDQ, parse_eml          # noqa: E402
from services.pii.agent import PiiScrubber                              # noqa: E402
from services.retrieval.agent import EvidenceSourcer                    # noqa: E402
from services.router.agent import ApprovalRouter                        # noqa: E402
from services.validator.agent import CitationVerifier                   # noqa: E402

import torch                                                            # noqa: E402
from opensearchpy import OpenSearch                                     # noqa: E402
from pymongo import MongoClient                                         # noqa: E402
from qdrant_client import QdrantClient                                  # noqa: E402
from qdrant_client.http import models as qm                             # noqa: E402
from sentence_transformers import SentenceTransformer                   # noqa: E402


PLATFORM_VERSION = "v0.2.0-agents"
TAXONOMY_VERSION = "tx_v0.1"
LIBRARY_VERSION = "lib_v0.1"
ENTITY = "BNY_MELLON_CORP"

OS_HOST = "http://localhost:9200"
OS_INDEX = "spans-v1"
QDRANT_HOST = "http://localhost:6333"
QDRANT_COLL = "spans_v1"
MODEL_NAME = "BAAI/bge-small-en-v1.5"

TOP_K = 10
TOP_N = 30
RRF_K = 60
BNY_SOURCES = ("edgar", "bny-ir")
FRAMEWORK_SOURCES = ("caiq", "ccm", "nist_csf", "nist_800_53", "afme")

RUNS_BUCKET = "bny-ddq-runs-sealed"
RUNS_DIR = MANIFESTS_DIR / "runs"
INBOX_DIR = MANIFESTS_DIR / "inbox"


# ── utility ──────────────────────────────────────────────────────
def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def short_hash(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


def chain_events(events: list[AgentEvent]) -> list[dict]:
    """Hash-chain events. prev_hash links each event to its predecessor."""
    prev = "sha256:" + "0" * 64
    chained = []
    for e in events:
        joined = (prev + e.event_id + e.payload_hash).encode("utf-8")
        chain_hash = "sha256:" + hashlib.sha256(joined).hexdigest()
        chained.append({
            "event_id": e.event_id, "kind": e.kind, "agent": e.agent,
            "agent_version": e.agent_version, "ts": e.ts,
            "payload": e.payload, "payload_hash": e.payload_hash,
            "prev_hash": prev, "chain_hash": chain_hash,
        })
        prev = chain_hash
    return chained


def merkle_root(hashes: list[str]) -> str:
    from core.domain.taxonomy import merkle_root as mr
    return mr(hashes)


# ── reverse lookup (lifted from 11_wire_up) ──────────────────────
def section_id_to_framework_ref(section_id: str, source: str,
                                 anchor_kind: str, anchor_path: str | None
                                 ) -> tuple[str, str, str] | None:
    if source == "caiq":
        parts = section_id.split(".")
        if len(parts) >= 3:
            return ("CAIQ", "v4.0.3", ".".join(parts[2:]))
    elif source == "ccm":
        parts = section_id.split(".")
        if len(parts) >= 3:
            return ("CCM", "v4.0.12", ".".join(parts[2:]))
    elif source == "nist_csf":
        if anchor_kind == "structural" and anchor_path:
            return ("NIST_CSF_v2.0", "v2.0", anchor_path)
    elif source == "nist_800_53":
        if anchor_kind == "structural" and anchor_path:
            return ("NIST_SP800_53_rev5", "rev5", anchor_path)
    elif source == "afme":
        if anchor_path:
            return ("AFME", "2026", f"AFME-{anchor_path}")
    return None


# ── orchestrator graph node: build candidate canonicals ──────────
def build_candidates(question_text: str, qdrant: QdrantClient, model, tax) -> list[dict]:
    vec = model.encode([question_text], normalize_embeddings=True,
                       convert_to_numpy=True)[0]
    qfilter = qm.Filter(should=[
        qm.FieldCondition(key="source", match=qm.MatchValue(value=src))
        for src in FRAMEWORK_SOURCES
    ])
    res = qdrant.query_points(
        collection_name=QDRANT_COLL, query=vec.tolist(), limit=10,
        query_filter=qfilter, with_payload=True,
    ).points
    candidates: list[dict] = []
    for p in res:
        pl = p.payload or {}
        ref = section_id_to_framework_ref(
            section_id=pl.get("section_id", ""),
            source=pl.get("source", ""),
            anchor_kind=pl.get("anchor_kind", ""),
            anchor_path=pl.get("anchor_path") or pl.get("anchor_item"),
        )
        if ref is None:
            continue
        framework, version, qref = ref
        canonical_id = tax.map_framework_question(framework, qref, version)
        if canonical_id:
            candidates.append({
                "canonical_id": canonical_id,
                "framework": framework, "version": version, "question_ref": qref,
                "dense_score": float(p.score),
                "span_id": pl.get("span_id"),
            })
    return candidates


# ── orchestrator graph node: hybrid retrieval ────────────────────
def retrieve_spans(question: str, os_client, qdrant, model) -> list[EvidenceSpan]:
    bm_body = {
        "size": TOP_N,
        "query": {
            "bool": {
                "must": [{"match": {"text": {"query": question, "operator": "or"}}}],
                "filter": [{"terms": {"source": list(BNY_SOURCES)}}],
            }
        },
        "_source": ["doc_id", "doc_hash", "section_id", "span_id", "span_hash",
                    "source", "form", "anchor_kind", "anchor_page", "anchor_item", "text"],
    }
    bm_resp = os_client.search(index=OS_INDEX, body=bm_body)
    bm = []
    for h in bm_resp["hits"]["hits"]:
        s = h["_source"]
        bm.append({**s, "score": h["_score"]})

    vec = model.encode([question], normalize_embeddings=True, convert_to_numpy=True)[0]
    qfilter = qm.Filter(should=[
        qm.FieldCondition(key="source", match=qm.MatchValue(value=src))
        for src in BNY_SOURCES
    ])
    dn_res = qdrant.query_points(
        collection_name=QDRANT_COLL, query=vec.tolist(), limit=TOP_N,
        query_filter=qfilter, with_payload=True,
    ).points
    dn = [{**(p.payload or {}), "score": p.score} for p in dn_res]

    scores: dict[str, float] = defaultdict(float)
    record: dict[str, dict] = {}
    for hits in (bm, dn):
        for rank, h in enumerate(hits):
            sid = h.get("span_id")
            if not sid:
                continue
            scores[sid] += 1.0 / (RRF_K + rank + 1)
            record.setdefault(sid, h)
    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:TOP_K]
    spans = []
    for sid, sc in fused:
        h = record[sid]
        spans.append(EvidenceSpan(
            span_id=sid, doc_id=h.get("doc_id"), doc_hash=h.get("doc_hash"),
            span_hash=h.get("span_hash"), source=h.get("source"), form=h.get("form"),
            anchor_kind=h.get("anchor_kind"),
            anchor_page=h.get("anchor_page"),
            anchor_item=h.get("anchor_item"),
            text=h.get("text", ""), score=float(sc),
        ))
    return spans


def fetch_span_lookup(citations, os_client) -> dict[str, str]:
    """span_hash → canonical text for the CitationVerifier."""
    if not citations:
        return {}
    body = {
        "size": 50,
        "query": {"terms": {"span_hash": [c.span_hash for c in citations]}},
        "_source": ["span_hash", "text"],
    }
    try:
        resp = os_client.search(index=OS_INDEX, body=body)
        return {h["_source"]["span_hash"]: h["_source"].get("text", "")
                for h in resp["hits"]["hits"]}
    except Exception:
        return {}


# ── tier picker (DraftComposer dispatch) ─────────────────────────
def pick_tier(canonical_id: Optional[str]) -> str:
    if not canonical_id:
        return "tier2_sonnet"
    if canonical_id.startswith(("canon.reg", "canon.cyber", "canon.is")):
        return "tier1_opus"
    return "tier2_sonnet"


# ── single-question pipeline ─────────────────────────────────────
def run_question(q, deps, agents, prior_responses_by_canon) -> dict:
    run_id = "run_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
    ctx = RunContext(
        run_id=run_id, taxonomy_version=TAXONOMY_VERSION,
        library_version=LIBRARY_VERSION, platform_version=PLATFORM_VERSION,
        entity=ENTITY,
    )
    started = time.time()

    # intake event
    ctx.emit(AgentEvent.make("Orchestrator", "1.0.0", "intake.received", {
        "question_id": q.question_id, "framework": q.framework,
        "raw_question_text_hash": short_hash(q.text),
    }))

    # 1. QuestionMapper
    candidates = build_candidates(q.text, deps["qdrant"], deps["model"], deps["tax"])
    mapper_out = agents["mapper"].run(QuestionMapperInput(
        question_id=q.question_id, framework=q.framework,
        raw_question_text=q.text, candidate_canonicals=candidates,
    ), ctx)

    # 2. library_lookup (orchestrator step, not an agent)
    library_entry = None
    library_entry_text = None
    if mapper_out.canonical_id:
        library_entry = deps["lib"].lookup(LibraryKey(
            canonical_id=mapper_out.canonical_id, entity=ENTITY, product=None,
        ))
    library_hit = library_entry is not None
    if library_entry:
        library_entry_text = library_entry.answer_text
    ctx.emit(AgentEvent.make("Orchestrator", "1.0.0", "library.lookup", {
        "canonical_id": mapper_out.canonical_id,
        "entity": ENTITY, "product": None,
        "hit": library_hit,
        "entry_id": library_entry.entry_id if library_entry else None,
    }))

    # 3. retrieve_evidence (hybrid BM25+dense+RRF over BNY corpus)
    retrieved = retrieve_spans(q.text, deps["os"], deps["qdrant"], deps["model"])
    ctx.emit(AgentEvent.make("Orchestrator", "1.0.0", "retrieve.hybrid", {
        "k": TOP_K, "filters": {"source": list(BNY_SOURCES)},
        "returned": len(retrieved),
        "top_score": retrieved[0].score if retrieved else 0.0,
        "top_3_sources": [s.source for s in retrieved[:3]],
    }))

    # 4. EvidenceSourcer (curate)
    sourcer_out = agents["sourcer"].run(EvidenceSourcerInput(
        question_id=q.question_id, raw_question_text=q.text,
        canonical_id=mapper_out.canonical_id,
        library_hit=library_hit,
        library_entry=({"answer_text": library_entry_text} if library_entry_text else None),
        retrieved_spans=retrieved,
    ), ctx)

    # 5. DraftComposer (tier-routed)
    tier = pick_tier(mapper_out.canonical_id)
    drafter_out = agents["drafter"].run(DraftComposerInput(
        question_id=q.question_id, raw_question_text=q.text,
        canonical_id=mapper_out.canonical_id, tier=tier,  # type: ignore[arg-type]
        evidence_bundle=sourcer_out.bundle,
        library_entry_text=library_entry_text,
    ), ctx)

    # 6. CitationVerifier
    span_lookup = fetch_span_lookup(drafter_out.citations, deps["os"])
    verifier_out = agents["verifier"].run(CitationVerifierInput(
        draft_text=drafter_out.draft_text,
        citations=drafter_out.citations,
        span_lookup=span_lookup,
    ), ctx)

    # 7. ConsistencyChecker
    prior = prior_responses_by_canon.get(mapper_out.canonical_id, [])
    consistency_out = agents["consistency"].run(ConsistencyCheckerInput(
        canonical_id=mapper_out.canonical_id,
        draft_text=drafter_out.draft_text,
        prior_responses=prior,
    ), ctx)

    # 8. PiiScrubber
    pii_out = agents["pii"].run(PiiScrubberInput(
        draft_text=drafter_out.draft_text or "",
    ), ctx)

    # 9. FreshnessAuditor (rule-based)
    fresh_out = agents["fresh"].run(FreshnessAuditorInput(
        library_entry=(asdict_safe(library_entry) if library_entry else None),
        evidence_bundle=sourcer_out.bundle,
        today=dt.date.today().isoformat(),
    ), ctx)

    # Aggregate guardrail verdict (validator-style):
    # any agent flag → escalate or halt.
    halt = (
        not verifier_out.all_pass
        or pii_out.halt
        or not drafter_out.draft_text
    )
    escalate = (
        consistency_out.drift_detected or fresh_out.stale
        or mapper_out.routed_to_sme
        or not sourcer_out.sufficient
    )
    validate_verdict = "halt" if halt else ("escalate" if escalate else "pass")
    ctx.emit(AgentEvent.make("Orchestrator", "1.0.0", "validate.aggregate", {
        "verdict": validate_verdict,
        "verifier_all_pass": verifier_out.all_pass,
        "pii_halt": pii_out.halt,
        "consistency_drift": consistency_out.drift_detected,
        "freshness_stale": fresh_out.stale,
        "draft_chars": len(drafter_out.draft_text),
        "sourcer_sufficient": sourcer_out.sufficient,
        "mapper_routed_to_sme": mapper_out.routed_to_sme,
    }))

    # 10. ApprovalRouter (rule-based)
    router_out = agents["router"].run(ApprovalRouterInput(
        canonical_id=mapper_out.canonical_id,
        classify_confidence=mapper_out.confidence,
        validate_verdict=validate_verdict,  # type: ignore[arg-type]
        pii_halt=pii_out.halt,
        freshness_stale=fresh_out.stale,
        consistency_drift=consistency_out.drift_detected,
    ), ctx)

    # 11. Seal response (L01 stand-in) — hash-chain + Merkle + S3.
    chained = chain_events(ctx.events)
    payload_hashes = [e["payload_hash"] for e in chained]
    root = merkle_root(payload_hashes)

    outbound_text = pii_out.clean_text or drafter_out.draft_text
    sealed = {
        "run_id": run_id,
        "ddq_id": q.ddq_id,
        "sealed_at": now_iso(),
        "platform_version": PLATFORM_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "library_version": LIBRARY_VERSION,
        "input": {
            "question_id": q.question_id, "framework": q.framework,
            "text": q.text,
        },
        "outbound_response": outbound_text,
        "outbound_response_hash": short_hash(outbound_text or ""),
        "evidence_refs": [
            {"span_id": c.span_id, "doc_hash": c.doc_hash, "span_hash": c.span_hash}
            for c in drafter_out.citations
        ],
        "agents": {
            "QuestionMapper":     {"canonical_id": mapper_out.canonical_id,
                                   "confidence": mapper_out.confidence,
                                   "routed_to_sme": mapper_out.routed_to_sme},
            "EvidenceSourcer":    {"selected": len(sourcer_out.bundle),
                                   "sufficient": sourcer_out.sufficient},
            "DraftComposer":      {"tier": drafter_out.tier_used,
                                   "draft_chars": len(drafter_out.draft_text),
                                   "used_library_entry": drafter_out.used_library_entry,
                                   "citation_count": len(drafter_out.citations)},
            "CitationVerifier":   {"all_pass": verifier_out.all_pass,
                                   "checked": len(verifier_out.results)},
            "ConsistencyChecker": {"consistent": consistency_out.consistent,
                                   "drift": consistency_out.drift_detected},
            "PiiScrubber":        {"findings": len(pii_out.findings),
                                   "halt": pii_out.halt},
            "FreshnessAuditor":   {"stale": fresh_out.stale,
                                   "reasons": fresh_out.reasons},
            "ApprovalRouter":     {"route": router_out.route,
                                   "queue": router_out.queue,
                                   "tier": router_out.tier},
        },
        "verdict": validate_verdict,
        "route": router_out.route,
        "events": chained,
        "merkle_root": root,
    }

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / f"{run_id}.json").write_text(json.dumps(sealed, indent=2), encoding="utf-8")
    body = json.dumps(sealed, indent=2).encode("utf-8")
    deps["s3"].put_object(
        Bucket=RUNS_BUCKET, Key=f"{run_id}/sealed.json", Body=body,
        ContentType="application/json",
        Metadata={"run_id": run_id, "verdict": validate_verdict,
                  "merkle_root": root, "platform_version": PLATFORM_VERSION},
    )

    return {
        "run_id": run_id, "question_id": q.question_id, "framework": q.framework,
        "canonical_id": mapper_out.canonical_id, "confidence": mapper_out.confidence,
        "library_hit": library_hit,
        "draft_chars": len(drafter_out.draft_text),
        "citation_count": len(drafter_out.citations),
        "validate_verdict": validate_verdict, "route": router_out.route,
        "queue": router_out.queue, "tier": router_out.tier,
        "elapsed_ms": int((time.time() - started) * 1000),
        "merkle_root": root,
        "outbound_preview": (outbound_text or "")[:300],
        "agent_events": len(ctx.events),
        "sealed": sealed,
    }


def asdict_safe(library_entry) -> dict:
    """Best-effort dict view of a LibraryEntry for FreshnessAuditor."""
    from dataclasses import is_dataclass, asdict
    if is_dataclass(library_entry):
        return asdict(library_entry)
    return dict(library_entry) if hasattr(library_entry, "__iter__") else {}


# ── main ─────────────────────────────────────────────────────────
def build_deps():
    print("== Loading backends ==")
    mongo = MongoClient("mongodb://ddq:ddq-dev@localhost:27018",
                        serverSelectionTimeoutMS=5000)
    s3 = s3_client()
    tax = MongoTaxonomy(mongo, s3)
    lib = MongoLibrary(mongo, s3)
    os_client = OpenSearch(OS_HOST, request_timeout=60)
    qdrant = QdrantClient(url=QDRANT_HOST, timeout=60)
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(MODEL_NAME, device=device)
    model.max_seq_length = 384
    return {"tax": tax, "lib": lib, "os": os_client, "qdrant": qdrant,
            "model": model, "s3": s3}


def build_agents():
    print("== Building agents (Anthropic SDK) ==")
    llm = AnthropicClient()
    return {
        "mapper":      QuestionMapper(llm),
        "sourcer":     EvidenceSourcer(llm),
        "drafter":     DraftComposer(llm),
        "verifier":    CitationVerifier(llm),
        "consistency": ConsistencyChecker(llm),
        "pii":         PiiScrubber(llm),
        "fresh":       FreshnessAuditor(),
        "router":      ApprovalRouter(),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--eml", required=True, help="Path to .eml file or inbox dir")
    p.add_argument("--max-questions", type=int, default=None,
                   help="Cap the number of questions processed (debug)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    eml_path = Path(args.eml)
    ddq = parse_eml(eml_path if eml_path.is_file() else next(eml_path.glob("*.eml")))
    print(f"\n== Ingested DDQ ==")
    print(f"  ddq_id      : {ddq.ddq_id}")
    print(f"  from        : {ddq.from_email}")
    print(f"  subject     : {ddq.subject}")
    print(f"  attachments : {ddq.attachments}")
    print(f"  questions   : {len(ddq.questions)}")
    print(f"  raw_sha256  : {ddq.raw_eml_sha256}\n")

    deps = build_deps()
    agents = build_agents()

    # In M1+ this comes from DuckDB.response_register. For now: empty.
    prior_responses_by_canon: dict = {}

    questions = ddq.questions[: args.max_questions] if args.max_questions else ddq.questions
    results = []
    for q in questions:
        # Attach ddq_id onto the question record for sealing.
        q.ddq_id = ddq.ddq_id  # type: ignore[attr-defined]
        print(f"-- {q.question_id} [{q.framework}]  {q.text[:100]}…")
        try:
            r = run_question(q, deps, agents, prior_responses_by_canon)
        except Exception as exc:
            print(f"   ✗ failed: {type(exc).__name__}: {exc}")
            results.append({"question_id": q.question_id, "error": str(exc),
                            "error_type": type(exc).__name__})
            continue
        results.append(r)
        print(f"   canonical={r['canonical_id']}  confidence={r['confidence']:.2f}"
              f"  library_hit={r['library_hit']}  tier={r['tier']}")
        print(f"   draft_chars={r['draft_chars']}  citations={r['citation_count']}"
              f"  verdict={r['validate_verdict']}  route={r['route']}  queue={r['queue']}")
        print(f"   {r['agent_events']} events  {r['elapsed_ms']}ms"
              f"  sealed s3://{RUNS_BUCKET}/{r['run_id']}/sealed.json")
        print(f"   preview: {r['outbound_preview'][:240]}\n")

    # Aggregated DDQ packet
    packet = {
        "ddq_id": ddq.ddq_id,
        "sealed_at": now_iso(),
        "platform_version": PLATFORM_VERSION,
        "from": ddq.from_email, "to": ddq.to_email, "subject": ddq.subject,
        "raw_eml_sha256": ddq.raw_eml_sha256,
        "question_count": len(questions),
        "results": [
            {k: v for k, v in r.items() if k != "sealed"}
            for r in results
        ],
    }
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    packet_path = INBOX_DIR / f"{ddq.ddq_id}.json"
    packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    deps["s3"].put_object(
        Bucket=RUNS_BUCKET, Key=f"inbox/{ddq.ddq_id}/sealed_packet.json",
        Body=json.dumps(packet, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    # Summary
    auto_approved = sum(1 for r in results if r.get("route") == "auto_approve")
    sme_queued = sum(1 for r in results if r.get("route") == "sme_queue")
    halted = sum(1 for r in results if r.get("route") == "halt")
    print("== DDQ summary ==")
    print(f"  packet      : {packet_path.relative_to(REPO_ROOT)}")
    print(f"  s3          : s3://{RUNS_BUCKET}/inbox/{ddq.ddq_id}/sealed_packet.json")
    print(f"  total       : {len(results)}")
    print(f"  auto_approve: {auto_approved}")
    print(f"  sme_queue   : {sme_queued}")
    print(f"  halt        : {halted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
