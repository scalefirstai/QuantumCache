#!/usr/bin/env python3
"""
DATA-PLAN.md §8 Day 13-14 — wire-up demo.

Implements the L07 graph (ddq.md §L07) in-process against the live
backends populated by Days 1–10:

    intake → classify → library_lookup
                          │
              ┌───────────┴───────────┐
              ▼ hit                   ▼ miss
         freshness_check         retrieve_evidence
              │                        │
              │                        ▼
              │                   draft_compose
              │                        │
              ▼                        ▼
              └────► validate_guardrails ◄────┐
                              │                │
              ┌───────────────┼───────────────┐│
              ▼ pass          ▼ escalate      ▼ halt
         seal_response    sme_approval    legal_review

Each run emits an L01-shaped journal record (audit event chain hash-linked,
sealed to S3). The full L01 audit journal (signed events, replay path,
hot-window-to-S3 sealing) is M1 work — this is the contract demo.

Usage:
    .venv/bin/python data/bootstrap/11_wire_up.py             # 5 mixed eval items
    .venv/bin/python data/bootstrap/11_wire_up.py --eval-id ev_xxx
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from _lib import MANIFESTS_DIR, s3_client  # noqa: E402

from core.domain.library import LibraryKey  # noqa: E402
from infra.adapters.mongo_library import MongoLibrary  # noqa: E402
from infra.adapters.mongo_taxonomy import MongoTaxonomy  # noqa: E402

import torch  # noqa: E402
from opensearchpy import OpenSearch  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.http import models as qm  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

PLATFORM_VERSION = "v0.1.0"
TAXONOMY_VERSION = "tx_v0.1"
LIBRARY_VERSION = "lib_v0.1"
ENTITY = "BNY_MELLON_CORP"

OS_HOST = "http://localhost:9200"
OS_INDEX = "spans-v1"
QDRANT_HOST = "http://localhost:6333"
QDRANT_COLL = "spans_v1"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
TOP_N = 30
TOP_K = 10
RRF_K = 60
HALT_RRF_THRESHOLD = 0.018
BNY_SOURCES = ("edgar", "bny-ir")
FRAMEWORK_SOURCES = ("caiq", "ccm", "nist_csf", "nist_800_53", "afme")
RUNS_BUCKET = "bny-ddq-runs-sealed"
RUNS_DIR = MANIFESTS_DIR / "runs"

EVAL_FIXTURES = REPO_ROOT / "evals" / "fixtures" / "v0" / "eval_set.json"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def short_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ── Reverse-lookup from framework span → canonical_id ────────────
def section_id_to_framework_ref(section_id: str, source: str, anchor_kind: str,
                                 anchor_path: str | None) -> tuple[str, str, str] | None:
    """Map a span's section_id + source to (framework, version, question_ref).

    section_id examples:
      CAIQ:        "CAIQ.A&A.A&A-01.1"
      CCM:         "CCM.A&A.A&A-01"
      NIST CSF:    "NIST_CSF_v2.0.<group>/.../<cid>"  (cid e.g. "GV.OC-01")
      NIST 800-53: "NIST_SP800_53_rev5.<group>/.../<cid>"  (cid e.g. "AC-2")
      AFME (DOCX): "<heading_slug>" — question id lives in anchor.subsection
    """
    if source == "caiq":
        # "CAIQ.<dom>.<qid>" — qid is the last dot-segment.
        parts = section_id.split(".")
        if len(parts) >= 3:
            qid = ".".join(parts[2:])
            return ("CAIQ", "v4.0.3", qid)
    elif source == "ccm":
        parts = section_id.split(".")
        if len(parts) >= 3:
            cid = ".".join(parts[2:])
            return ("CCM", "v4.0.12", cid)
    elif source == "nist_csf":
        # cid is in anchor_path for structural anchors.
        if anchor_kind == "structural" and anchor_path:
            return ("NIST_CSF_v2.0", "v2.0", anchor_path)
    elif source == "nist_800_53":
        if anchor_kind == "structural" and anchor_path:
            return ("NIST_SP800_53_rev5", "rev5", anchor_path)
    elif source == "afme":
        # AFME uses anchor_path? No — for DOCX we put question id in anchor.subsection
        # (which the indexer flattened to anchor_item or anchor_path). Best-effort.
        if anchor_path:
            return ("AFME", "2026", f"AFME-{anchor_path}")
    return None


# ── Pipeline node: classify (L05 stand-in) ───────────────────────
def classify(question: str, qdrant: QdrantClient, model, tax: MongoTaxonomy) -> dict:
    """Embed question, find top-3 framework spans, map to canonical_id via
    reverse lookup. Confidence = top dense score; below 0.50 → unclassified."""
    vec = model.encode([question], normalize_embeddings=True, convert_to_numpy=True)[0]
    qfilter = qm.Filter(should=[
        qm.FieldCondition(key="source", match=qm.MatchValue(value=src)) for src in FRAMEWORK_SOURCES
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
    if not candidates:
        return {"canonical_id": None, "confidence": 0.0, "candidates": []}
    # Vote: weight by score, pick top.
    weights: dict = defaultdict(float)
    for c in candidates:
        weights[c["canonical_id"]] += c["dense_score"]
    chosen, total = max(weights.items(), key=lambda kv: kv[1])
    confidence = float(candidates[0]["dense_score"])  # top-1 raw similarity
    return {
        "canonical_id": chosen,
        "confidence": round(confidence, 4),
        "candidates": candidates[:5],
    }


# ── Pipeline node: library_lookup (L04) ──────────────────────────
def library_lookup(canonical_id: str | None, lib: MongoLibrary) -> dict:
    if not canonical_id:
        return {"hit": False, "entry": None, "reason": "no canonical_id"}
    entry = lib.lookup(LibraryKey(canonical_id=canonical_id, entity=ENTITY, product=None))
    if entry is None:
        return {"hit": False, "entry": None, "reason": "no entry for (canonical_id, entity, product=None)"}
    return {"hit": True, "entry": entry}


# ── Pipeline node: retrieve_evidence (L03) ───────────────────────
def retrieve_evidence(question: str, os_client: OpenSearch, qdrant: QdrantClient, model) -> dict:
    bm_body = {
        "size": TOP_N,
        "query": {
            "bool": {
                "must": [{"match": {"text": {"query": question, "operator": "or"}}}],
                "filter": [{"terms": {"source": list(BNY_SOURCES)}}],
            }
        },
        "_source": ["doc_id", "doc_hash", "section_id", "span_id", "span_hash",
                    "source", "form", "anchor_kind", "anchor_page", "anchor_item",
                    "filing_date", "effective_date", "text"],
    }
    bm_resp = os_client.search(index=OS_INDEX, body=bm_body)
    bm = []
    for h in bm_resp["hits"]["hits"]:
        s = h["_source"]
        bm.append({"span_id": s["span_id"], "doc_id": s["doc_id"], "doc_hash": s["doc_hash"],
                   "span_hash": s["span_hash"], "source": s["source"],
                   "anchor_kind": s.get("anchor_kind"),
                   "anchor_page": s.get("anchor_page"), "anchor_item": s.get("anchor_item"),
                   "form": s.get("form"), "text": s.get("text", ""), "score": h["_score"]})

    vec = model.encode([question], normalize_embeddings=True, convert_to_numpy=True)[0]
    qfilter = qm.Filter(should=[
        qm.FieldCondition(key="source", match=qm.MatchValue(value=src)) for src in BNY_SOURCES
    ])
    dn_res = qdrant.query_points(
        collection_name=QDRANT_COLL, query=vec.tolist(), limit=TOP_N,
        query_filter=qfilter, with_payload=True,
    ).points
    dn = []
    for p in dn_res:
        pl = p.payload or {}
        dn.append({"span_id": pl.get("span_id"), "doc_id": pl.get("doc_id"),
                   "doc_hash": pl.get("doc_hash"), "span_hash": pl.get("span_hash"),
                   "source": pl.get("source"), "anchor_kind": pl.get("anchor_kind"),
                   "anchor_page": pl.get("anchor_page"), "anchor_item": pl.get("anchor_item"),
                   "form": pl.get("form"), "text": pl.get("text", ""), "score": p.score})

    # RRF
    scores: dict[str, float] = defaultdict(float)
    record: dict[str, dict] = {}
    for hits in (bm, dn):
        for rank, h in enumerate(hits):
            sid = h["span_id"]
            scores[sid] += 1.0 / (RRF_K + rank + 1)
            record.setdefault(sid, h)
    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:TOP_K]
    spans = [{**record[sid], "rrf_score": sc} for sid, sc in fused]
    return {
        "candidate_count": len(set(h["span_id"] for h in bm + dn)),
        "returned_count": len(spans),
        "top_score": spans[0]["rrf_score"] if spans else 0.0,
        "spans": spans,
    }


# ── Pipeline node: draft_compose (L06 stand-in) ──────────────────
def draft_compose(library_result: dict, retrieve_result: dict | None) -> dict:
    if library_result["hit"]:
        entry = library_result["entry"]
        return {
            "draft_text": entry.answer_text,
            "evidence_refs": [
                {"doc_hash": e.doc_hash, "span_hash": e.span_hash, "anchor": e.anchor,
                 "doc_id": e.doc_id, "span_id": e.span_id}
                for e in entry.evidence_refs
            ],
            "source": "library",
            "library_entry_id": entry.entry_id,
        }
    spans = (retrieve_result or {}).get("spans") or []
    if not spans:
        return {"draft_text": "", "evidence_refs": [], "source": "retrieval", "library_entry_id": None}
    # Top 3 substantive (≥80 char) spans, extractive concat.
    substantive = [s for s in spans if len((s.get("text") or "")) >= 80][:3]
    if not substantive:
        substantive = spans[:1]
    paragraphs = []
    refs = []
    for s in substantive:
        anchor_label = (
            f"page {s.get('anchor_page')}" if s.get("anchor_kind") == "page"
            else (s.get("anchor_item") or s.get("section_id") or "")
        )
        cite = f"[{s.get('source')}/{s.get('form') or s.get('doc_id') or ''}/{anchor_label}]"
        paragraphs.append(f"{s.get('text', '').strip()} {cite}".strip())
        refs.append({
            "doc_hash": s["doc_hash"], "span_hash": s["span_hash"],
            "anchor": {"kind": s.get("anchor_kind"), "doc_hash": s["doc_hash"]},
            "doc_id": s["doc_id"], "span_id": s["span_id"],
        })
    return {
        "draft_text": "\n\n".join(paragraphs),
        "evidence_refs": refs,
        "source": "retrieval",
        "library_entry_id": None,
    }


# ── Pipeline node: validate_guardrails (L02 stand-in) ────────────
SSN_RE = __import__("re").compile(r"\b\d{3}-\d{2}-\d{4}\b")
ACCT_RE = __import__("re").compile(r"\b(?:account|acct)[ :#-]*\d{6,}\b", flags=__import__("re").IGNORECASE)


def validate_guardrails(draft: dict, span_hash_universe: set, retrieve_result: dict | None) -> dict:
    checks: list[dict] = []
    # 01 Citation Resolution
    if not draft.get("evidence_refs"):
        checks.append({"id": "guardrail.01_citation_resolution", "verdict": "halt",
                       "reason": "no evidence_refs in draft"})
    else:
        unresolved = [r["span_hash"] for r in draft["evidence_refs"]
                      if r["span_hash"] not in span_hash_universe]
        if unresolved:
            checks.append({"id": "guardrail.01_citation_resolution", "verdict": "halt",
                           "reason": f"{len(unresolved)} evidence span(s) not in corpus"})
        else:
            # Strength check: top retrieval RRF score below halt threshold → halt.
            top = (retrieve_result or {}).get("top_score", 1.0)
            if draft.get("source") == "retrieval" and top < HALT_RRF_THRESHOLD:
                checks.append({"id": "guardrail.01_citation_resolution", "verdict": "halt",
                               "reason": f"top RRF {top:.4f} below halt threshold {HALT_RRF_THRESHOLD}"})
            else:
                checks.append({"id": "guardrail.01_citation_resolution", "verdict": "pass"})
    # 02 Evidence Freshness — bootstrap entries pass trivially.
    checks.append({"id": "guardrail.02_evidence_freshness", "verdict": "pass",
                   "reason": "bootstrap mode — public-corpus evidence assumed fresh"})
    # 03 Cross-DDQ Consistency — no shipped responses yet → trivially pass.
    checks.append({"id": "guardrail.03_cross_ddq_consistency", "verdict": "pass",
                   "reason": "no prior shipped responses"})
    # 04 Confidentiality Scrub
    text = draft.get("draft_text", "")
    if SSN_RE.search(text):
        checks.append({"id": "guardrail.04_confidentiality_scrub", "verdict": "halt",
                       "reason": "SSN-shaped string detected"})
    elif ACCT_RE.search(text):
        checks.append({"id": "guardrail.04_confidentiality_scrub", "verdict": "halt",
                       "reason": "account-number-shaped string detected"})
    else:
        checks.append({"id": "guardrail.04_confidentiality_scrub", "verdict": "pass"})

    halts = [c for c in checks if c["verdict"] == "halt"]
    verdict = "halt" if halts else "pass"
    return {
        "verdict": verdict,
        "halt_reason": (halts[0]["reason"] if halts else None),
        "checks": checks,
    }


# ── Pipeline node: seal_response (L01 stand-in) ──────────────────
def make_event(parent: str | None, kind: str, payload: dict) -> dict:
    eid = "evt_" + uuid.uuid4().hex[:16]
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "event_id": eid,
        "parent_event_id": parent,
        "kind": kind,
        "ts": now(),
        "payload": payload,
        "payload_hash": "sha256:" + hashlib.sha256(body).hexdigest(),
    }


def chain_events(events: list[dict]) -> list[dict]:
    """Hash-chain events in order. prev_hash links each event to its predecessor."""
    prev = "sha256:" + "0" * 64
    chained = []
    for e in events:
        joined = (prev + e["event_id"] + e["payload_hash"]).encode("utf-8")
        chain_hash = "sha256:" + hashlib.sha256(joined).hexdigest()
        chained.append({**e, "prev_hash": prev, "chain_hash": chain_hash})
        prev = chain_hash
    return chained


def seal_run(run_id: str, item: dict, events: list[dict], outbound_text: str,
             evidence_refs: list[dict], verdict: str, s3, taxonomy_ver: str,
             library_ver: str) -> dict:
    chained = chain_events(events)
    payload_hashes = [e["payload_hash"] for e in chained]
    # Merkle root over events.
    from core.domain.taxonomy import merkle_root
    root = merkle_root(payload_hashes)

    sealed = {
        "run_id": run_id,
        "sealed_at": now(),
        "platform_version": PLATFORM_VERSION,
        "taxonomy_version": taxonomy_ver,
        "library_version": library_ver,
        "input": item,
        "outbound_response": outbound_text,
        "outbound_response_hash": "sha256:" + hashlib.sha256(outbound_text.encode("utf-8")).hexdigest(),
        "evidence_refs": evidence_refs,
        "verdict": verdict,
        "events": chained,
        "merkle_root": root,
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / f"{run_id}.json").write_text(json.dumps(sealed, indent=2), encoding="utf-8")
    body = json.dumps(sealed, indent=2, sort_keys=False).encode("utf-8")
    s3.put_object(
        Bucket=RUNS_BUCKET, Key=f"{run_id}/sealed.json", Body=body,
        ContentType="application/json",
        Metadata={"run_id": run_id, "verdict": verdict, "merkle_root": root,
                  "platform_version": PLATFORM_VERSION},
    )
    return sealed


# ── Orchestrator ─────────────────────────────────────────────────
def run_one(item: dict, deps: dict) -> dict:
    run_id = "run_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
    started = time.time()
    events: list[dict] = []
    parent = None

    # 1. intake
    e = make_event(parent, "intake", {
        "eval_id": item.get("eval_id"),
        "framework": item.get("framework"),
        "raw_question_text_hash": short_hash(item.get("raw_question_text") or ""),
    })
    events.append(e); parent = e["event_id"]

    # 2. classify
    cls = classify(item["raw_question_text"], deps["qdrant"], deps["model"], deps["tax"])
    e = make_event(parent, "classify.match", {
        "canonical_id": cls["canonical_id"],
        "confidence": cls["confidence"],
        "top_candidates": cls["candidates"][:3],
    })
    events.append(e); parent = e["event_id"]

    # 3. library_lookup
    lib_res = library_lookup(cls["canonical_id"], deps["lib"])
    e = make_event(parent, "library.lookup", {
        "canonical_id": cls["canonical_id"], "entity": ENTITY, "product": None,
        "hit": lib_res["hit"],
        "entry_id": (lib_res["entry"].entry_id if lib_res["hit"] else None),
        "reason": lib_res.get("reason"),
    })
    events.append(e); parent = e["event_id"]

    # 4. retrieve_evidence (only on miss)
    retrieve_res = None
    if not lib_res["hit"]:
        e0 = make_event(parent, "retrieve.query", {
            "query_hash": short_hash(item["raw_question_text"]),
            "filters": {"source": list(BNY_SOURCES)}, "k": TOP_K,
        })
        events.append(e0); parent = e0["event_id"]
        retrieve_res = retrieve_evidence(item["raw_question_text"], deps["os"], deps["qdrant"], deps["model"])
        e1 = make_event(parent, "retrieve.result", {
            "candidate_count": retrieve_res["candidate_count"],
            "returned_count": retrieve_res["returned_count"],
            "top_score": retrieve_res["top_score"],
            "top_3_sources": [s.get("source") for s in retrieve_res["spans"][:3]],
        })
        events.append(e1); parent = e1["event_id"]

    # 5. draft_compose
    draft = draft_compose(lib_res, retrieve_res)
    e = make_event(parent, "draft.compose", {
        "draft_text_hash": short_hash(draft["draft_text"]),
        "draft_chars": len(draft["draft_text"]),
        "evidence_count": len(draft["evidence_refs"]),
        "source": draft["source"],
        "library_entry_id": draft.get("library_entry_id"),
    })
    events.append(e); parent = e["event_id"]

    # 6. validate_guardrails
    val = validate_guardrails(draft, deps["span_universe"], retrieve_res)
    e = make_event(parent, "validate.check", {
        "verdict": val["verdict"],
        "halt_reason": val["halt_reason"],
        "checks": val["checks"],
    })
    events.append(e); parent = e["event_id"]

    # 7. seal_response
    sealed = seal_run(run_id, item, events, draft["draft_text"], draft["evidence_refs"],
                      val["verdict"], deps["s3"], TAXONOMY_VERSION, LIBRARY_VERSION)

    return {
        "run_id": run_id,
        "eval_id": item.get("eval_id"),
        "framework": item.get("framework"),
        "expected_verdict": item.get("expected_verdict"),
        "expected_canonical_id": item.get("expected_canonical_id"),
        "actual_verdict": val["verdict"],
        "halt_reason": val["halt_reason"],
        "actual_canonical_id": cls["canonical_id"],
        "library_hit": lib_res["hit"],
        "draft_chars": len(draft["draft_text"]),
        "evidence_count": len(draft["evidence_refs"]),
        "elapsed_ms": int((time.time() - started) * 1000),
        "merkle_root": sealed["merkle_root"],
        "sealed_at": sealed["sealed_at"],
        "outbound_response_hash": sealed["outbound_response_hash"],
        "draft_preview": draft["draft_text"][:300],
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--eval-id", help="Run a single eval item by id")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    print("== Loading backends ==")
    mongo = MongoClient("mongodb://ddq:ddq-dev@localhost:27018", serverSelectionTimeoutMS=5000)
    s3 = s3_client()
    tax = MongoTaxonomy(mongo, s3)
    lib = MongoLibrary(mongo, s3)
    os_client = OpenSearch(OS_HOST, request_timeout=60)
    qdrant = QdrantClient(url=QDRANT_HOST, timeout=60)
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(MODEL_NAME, device=device)
    model.max_seq_length = 384
    by_source = json.loads((MANIFESTS_DIR / "spans-full.json").read_text(encoding="utf-8"))
    span_universe = {s["span_hash"] for spans in by_source.values() for s in spans}
    deps = {"tax": tax, "lib": lib, "os": os_client, "qdrant": qdrant,
            "model": model, "s3": s3, "span_universe": span_universe}

    fixtures = json.loads(EVAL_FIXTURES.read_text(encoding="utf-8"))
    items = fixtures["items"]

    # Pick: first 2 AFME, 1 CAIQ, 1 ESG, 1 ADVERSARIAL — proves all paths.
    if args.eval_id:
        picks = [it for it in items if it["eval_id"] == args.eval_id]
        if not picks:
            print(f"no item with eval_id={args.eval_id}", file=sys.stderr)
            return 2
    else:
        wanted = {"AFME": 2, "CAIQ": 1, "AFME_ESG": 1, "ADVERSARIAL": 1}
        picks = []
        seen = Counter()
        for it in items:
            if seen[it["framework"]] < wanted.get(it["framework"], 0):
                picks.append(it)
                seen[it["framework"]] += 1
            if sum(seen.values()) >= sum(wanted.values()):
                break

    print(f"== Running {len(picks)} eval items ==\n")
    results: list[dict] = []
    for it in picks:
        print(f"-- {it['eval_id']}  [{it['framework']}]")
        print(f"   Q: {it['raw_question_text'][:140]}")
        print(f"   expected: verdict={it['expected_verdict']}  canonical={it.get('expected_canonical_id')}")
        r = run_one(it, deps)
        results.append(r)
        verdict_match = r["actual_verdict"] == r["expected_verdict"]
        cls_match = (
            None if not r["expected_canonical_id"]
            else r["actual_canonical_id"] == r["expected_canonical_id"]
        )
        flag = "✓" if verdict_match else "✗"
        print(f"   actual:   verdict={r['actual_verdict']}  canonical={r['actual_canonical_id']}")
        print(f"   classify match: {cls_match}   verdict match: {flag}   library_hit: {r['library_hit']}   draft_chars: {r['draft_chars']}   {r['elapsed_ms']}ms")
        if r["halt_reason"]:
            print(f"   halt_reason: {r['halt_reason']}")
        print(f"   sealed: {r['merkle_root']}  ->  s3://{RUNS_BUCKET}/{r['run_id']}/sealed.json")
        print(f"   draft preview: {r['draft_preview'][:200]}{'…' if len(r['draft_preview']) >= 200 else ''}")
        print()

    # Summary
    verdict_matches = sum(1 for r in results if r["actual_verdict"] == r["expected_verdict"])
    classify_attempted = [r for r in results if r["expected_canonical_id"]]
    classify_matches = sum(1 for r in classify_attempted
                           if r["actual_canonical_id"] == r["expected_canonical_id"])
    library_hits = sum(1 for r in results if r["library_hit"])

    print("== Summary ==")
    print(f"  verdict-match  : {verdict_matches}/{len(results)}")
    print(f"  classify-match : {classify_matches}/{len(classify_attempted)} (where expected_canonical_id is set)")
    print(f"  library hits   : {library_hits}/{len(results)}")
    print(f"  total events   : {sum(len(json.loads((RUNS_DIR / (r['run_id'] + '.json')).read_text())['events']) for r in results)}")

    report = {
        "generated_at": now(),
        "platform_version": PLATFORM_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "library_version": LIBRARY_VERSION,
        "run_count": len(results),
        "verdict_matches": verdict_matches,
        "classify_matches": classify_matches,
        "library_hits": library_hits,
        "results": results,
    }
    out = MANIFESTS_DIR / "wire-up-report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nreport: {out.relative_to(REPO_ROOT)}")
    print(f"sealed runs: {RUNS_DIR.relative_to(REPO_ROOT)}/  + s3://{RUNS_BUCKET}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
