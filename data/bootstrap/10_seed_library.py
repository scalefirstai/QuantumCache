#!/usr/bin/env python3
"""
DATA-PLAN.md §8 Day 9 — answer library v0 (~50 SME-stub entries).

For each canonical that's plausibly answerable from the BNY public corpus,
run a hybrid query filtered to `source ∈ {edgar, bny-ir}`, score by top
RRF rank, take the top N (default 60 attempts → 50 keepers after validator).
Build an extractive `LibraryEntry` per pick: top 1–3 evidence spans become
the evidence_refs and answer_text body; SME refines later.

Per DATA-PLAN §5 invariants:
  - Bootstrap entries tagged ["bootstrap", "public-only"]; OPA must exclude
    these from production response paths until SME re-approval.
  - approvers = [{role: "bootstrap.seed"}] only.
  - Extractive over generative for facts (ddq.md §1 invariant 4).

Run from repo root:
    .venv/bin/python data/bootstrap/10_seed_library.py
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from _lib import MANIFESTS_DIR, s3_client  # noqa: E402

from core.domain.library import (  # noqa: E402
    Approver,
    EvidenceRef,
    LibraryEntry,
)
from core.domain.taxonomy import CanonicalQuestion, FrameworkMapping  # noqa: E402
from infra.adapters.mongo_taxonomy import MongoTaxonomy  # noqa: E402
from infra.adapters.mongo_library import MongoLibrary, SNAPSHOT_BUCKET  # noqa: E402

import torch  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from opensearchpy import OpenSearch  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.http import models as qm  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

OS_HOST = "http://localhost:9200"
OS_INDEX = "spans-v1"
QDRANT_HOST = "http://localhost:6333"
QDRANT_COLL = "spans_v1"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
TOP_N = 30                # candidates per backend
EVIDENCE_PER_ENTRY = 3
RRF_K = 60
ENTITY = "BNY_MELLON_CORP"
LIBRARY_VERSION = "lib_v0.1"
PRIVKEY_PATH = REPO_ROOT / "data/manifests/keys/taxonomy_signing_dev.priv.pem"

# Domains where BNY public corpus plausibly answers something.
# Skip the rest (canon.is.crypto, canon.cyber, canon.esg) — they need internal evidence.
PRIORITY_TOPS = (
    "canon.reg",
    "canon.or",
    "canon.subc",
    "canon.is.audit",       # 10-K mentions auditor + scope
    "canon.is.hr_security", # proxy mentions training/HR
)

# PII detector — bootstrap-public so should never trigger; sanity check anyway.
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
ACCOUNT_NUMBER_RE = re.compile(r"\b(?:account|acct)[ :#-]*\d{6,}\b", re.I)


# ── retrieval ────────────────────────────────────────────────────
def bm25_search(client: OpenSearch, query: str, n: int) -> list[dict]:
    body = {
        "size": n,
        "query": {
            "bool": {
                "must": [{"match": {"text": {"query": query, "operator": "or"}}}],
                "filter": [{"terms": {"source": ["edgar", "bny-ir"]}}],
            }
        },
        "_source": ["doc_id", "doc_hash", "section_id", "span_id", "span_hash",
                    "source", "form", "anchor_kind", "anchor_page", "anchor_item",
                    "filing_date", "effective_date", "text"],
    }
    resp = client.search(index=OS_INDEX, body=body)
    out = []
    for h in resp["hits"]["hits"]:
        s = h["_source"]
        out.append({
            "span_id": s["span_id"], "doc_id": s["doc_id"], "doc_hash": s["doc_hash"],
            "span_hash": s["span_hash"], "source": s["source"],
            "anchor_kind": s.get("anchor_kind"),
            "anchor_page": s.get("anchor_page"),
            "anchor_item": s.get("anchor_item"),
            "form": s.get("form"), "filing_date": s.get("filing_date"),
            "effective_date": s.get("effective_date"),
            "text": s.get("text", ""), "score": h["_score"],
        })
    return out


def dense_search(qdrant: QdrantClient, model, query: str, n: int) -> list[dict]:
    vec = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
    qfilter = qm.Filter(must=[
        qm.Filter(should=[
            qm.FieldCondition(key="source", match=qm.MatchValue(value="edgar")),
            qm.FieldCondition(key="source", match=qm.MatchValue(value="bny-ir")),
        ])
    ])
    res = qdrant.query_points(
        collection_name=QDRANT_COLL, query=vec.tolist(), limit=n,
        query_filter=qfilter, with_payload=True,
    ).points
    out = []
    for p in res:
        pl = p.payload or {}
        out.append({
            "span_id": pl.get("span_id"), "doc_id": pl.get("doc_id"), "doc_hash": pl.get("doc_hash"),
            "span_hash": pl.get("span_hash"), "source": pl.get("source"),
            "anchor_kind": pl.get("anchor_kind"),
            "anchor_page": pl.get("anchor_page"),
            "anchor_item": pl.get("anchor_item"),
            "form": pl.get("form"), "filing_date": pl.get("filing_date"),
            "effective_date": pl.get("effective_date"),
            "text": pl.get("text", ""), "score": p.score,
        })
    return out


def rrf(rankings: list[list[dict]], k: int = RRF_K, top_k: int = 10) -> list[dict]:
    scores: dict[str, float] = {}
    record: dict[str, dict] = {}
    for hits in rankings:
        for rank, h in enumerate(hits):
            sid = h["span_id"]
            scores[sid] = scores.get(sid, 0.0) + 1.0 / (k + rank + 1)
            record.setdefault(sid, h)
    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return [{**record[sid], "rrf_score": sc} for sid, sc in fused]


# ── library entry construction ───────────────────────────────────
def anchor_from_hit(h: dict) -> dict:
    if h.get("anchor_kind") == "page":
        return {"kind": "page", "page": h.get("anchor_page"), "doc_hash": h["doc_hash"]}
    if h.get("anchor_kind") == "section":
        return {"kind": "section", "item": h.get("anchor_item"), "subsection": None,
                "doc_hash": h["doc_hash"]}
    return {"kind": h.get("anchor_kind") or "section", "doc_hash": h["doc_hash"]}


def build_entry(canonical: CanonicalQuestion, hits: list[dict]) -> LibraryEntry:
    today = dt.date.today()
    evidence_refs = [
        EvidenceRef(
            doc_hash=h["doc_hash"], span_hash=h["span_hash"],
            anchor=anchor_from_hit(h),
            doc_id=h.get("doc_id"), span_id=h.get("span_id"),
            score=round(h.get("rrf_score") or 0.0, 6),
            excerpt=(h.get("text") or "")[:400],
        )
        for h in hits[:EVIDENCE_PER_ENTRY]
    ]
    paragraphs = []
    for h in hits[:EVIDENCE_PER_ENTRY]:
        text = (h.get("text") or "").strip()
        anchor_label = (
            f"page {h.get('anchor_page')}" if h.get("anchor_kind") == "page"
            else (h.get("anchor_item") or "")
        )
        cite = f"[{h.get('source')}/{h.get('form') or h.get('doc_id') or ''}/{anchor_label}]"
        paragraphs.append(f"{text} {cite}".strip())
    answer_text = "\n\n".join(paragraphs)

    entry_id = f"lib_bootstrap_{canonical.canonical_id.replace('.', '_')}"
    return LibraryEntry(
        entry_id=entry_id,
        canonical_id=canonical.canonical_id,
        entity=ENTITY,
        product=None,
        answer_text=answer_text,
        evidence_refs=evidence_refs,
        approvers=[Approver(
            user_id="bootstrap",
            role="bootstrap.seed",
            ts=dt.datetime.now(dt.timezone.utc).isoformat(),
            comment="auto-generated from public corpus; demo-grade only",
        )],
        effective_date=today.isoformat(),
        expiry_date=(today + dt.timedelta(days=365)).isoformat(),
        review_due=(today + dt.timedelta(days=180)).isoformat(),
        version=1,
        tags=["bootstrap", "public-only"],
        do_not_answer=False,
    )


# ── mini validator (ddq.md §L02 stand-in) ────────────────────────
def validate_entry(entry: LibraryEntry, span_hash_universe: set[str]) -> tuple[bool, list[str]]:
    """Returns (passes, list of failure reasons)."""
    reasons: list[str] = []
    # 1. Citation Resolution: ≥1 evidence_ref; every span_hash exists.
    if not entry.evidence_refs:
        reasons.append("citation_resolution: no evidence_refs")
    for ref in entry.evidence_refs:
        if ref.span_hash not in span_hash_universe:
            reasons.append(f"citation_resolution: span_hash not in corpus: {ref.span_hash[:24]}…")
    # 2. Evidence Freshness: bootstrap entries get a synthetic effective_date == today; pass.
    try:
        eff = dt.date.fromisoformat(entry.effective_date)
        if (dt.date.today() - eff).days > 30:
            reasons.append("evidence_freshness: effective_date too old for bootstrap entry")
    except (TypeError, ValueError):
        reasons.append(f"evidence_freshness: malformed effective_date {entry.effective_date!r}")
    # 3. Cross-DDQ Consistency: trivially true at bootstrap (no prior shipped responses).
    # 4. Confidentiality Scrub: PII regex sweep on answer_text.
    if SSN_RE.search(entry.answer_text):
        reasons.append("confidentiality_scrub: SSN-shaped string detected")
    if ACCOUNT_NUMBER_RE.search(entry.answer_text):
        reasons.append("confidentiality_scrub: account-number-shaped string detected")
    return (not reasons), reasons


# ── main ─────────────────────────────────────────────────────────
def main() -> int:
    print("== Connecting to backends ==")
    mongo = MongoClient("mongodb://ddq:ddq-dev@localhost:27018", serverSelectionTimeoutMS=5000)
    s3 = s3_client()
    tax = MongoTaxonomy(mongo, s3)
    lib = MongoLibrary(mongo, s3)
    os_client = OpenSearch(OS_HOST, request_timeout=60)
    qdrant = QdrantClient(url=QDRANT_HOST, timeout=60)
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(MODEL_NAME, device=device)
    model.max_seq_length = 384

    # Load span-hash universe for the validator.
    by_source = json.loads((MANIFESTS_DIR / "spans-full.json").read_text(encoding="utf-8"))
    span_hash_universe = {s["span_hash"] for spans in by_source.values() for s in spans}
    print(f"  span universe: {len(span_hash_universe):,} spans")

    canonicals = list(tax.list_all())
    candidates = [c for c in canonicals if any(c.canonical_id.startswith(p) for p in PRIORITY_TOPS)]
    print(f"  taxonomy: {len(canonicals)} canonicals; {len(candidates)} match priority tops")

    print("\n== Stage 1: hybrid retrieval over BNY corpus ==")
    scored: list[tuple[CanonicalQuestion, list[dict], float]] = []
    t0 = time.time()
    for i, c in enumerate(candidates):
        # Use label + description as query (description holds the full question text).
        query = (c.label + ". " + c.description).strip()
        if len(query) < 20:
            continue
        bm = bm25_search(os_client, query, TOP_N)
        dn = dense_search(qdrant, model, query, TOP_N)
        fu = rrf([bm, dn], top_k=10)
        if not fu:
            continue
        # Require the top hit text to be substantive (>= 80 chars) to avoid stub picks.
        substantive = [h for h in fu if len((h.get("text") or "")) >= 80]
        if not substantive:
            continue
        scored.append((c, substantive, substantive[0]["rrf_score"]))
        if (i + 1) % 50 == 0:
            print(f"  scored {i+1}/{len(candidates)} ({time.time()-t0:.1f}s)")
    print(f"  scored: {len(scored)} canonicals in {time.time()-t0:.1f}s")

    # Sort by score, take top N attempts.
    scored.sort(key=lambda t: t[2], reverse=True)
    target_attempts = 60   # we want 50 to pass validator
    picks = scored[:target_attempts]
    print(f"\n== Stage 2: build entries for top {len(picks)} canonicals ==")
    print("  by top-level domain:")
    by_top: dict[str, int] = {}
    for c, _, _ in picks:
        top = ".".join(c.canonical_id.split(".")[:2])
        by_top[top] = by_top.get(top, 0) + 1
    for k, v in sorted(by_top.items()):
        print(f"     {k:<20} {v}")

    print("\n== Stage 3: validator (ddq.md §L02 stand-in) ==")
    entries: list[LibraryEntry] = []
    failures: list[dict] = []
    for c, hits, score in picks:
        entry = build_entry(c, hits)
        passes, reasons = validate_entry(entry, span_hash_universe)
        if passes:
            entries.append(entry)
        else:
            failures.append({"canonical_id": c.canonical_id, "score": score, "reasons": reasons})
    print(f"  validated: {len(entries)} pass, {len(failures)} fail")
    for f in failures[:5]:
        print(f"    FAIL  {f['canonical_id']}  {f['reasons']}")

    if len(entries) < 50:
        # Backfill from remaining scored canonicals.
        idx = target_attempts
        while len(entries) < 50 and idx < len(scored):
            c, hits, score = scored[idx]
            idx += 1
            entry = build_entry(c, hits)
            passes, reasons = validate_entry(entry, span_hash_universe)
            if passes:
                entries.append(entry)
        print(f"  after backfill: {len(entries)} entries")

    print("\n== Stage 4: write to Mongo + cut signed snapshot ==")
    lib.coll.delete_many({})  # idempotent rebuild
    for e in entries:
        lib.upsert(e)
    print(f"  upserted: {len(entries)}")

    priv_pem = PRIVKEY_PATH.read_bytes()
    snap = lib.cut_version(LIBRARY_VERSION, signer_id="dev.bootstrap@local",
                           signer_priv_key_pem=priv_pem)
    print(f"  snapshot {LIBRARY_VERSION} sealed:")
    print(f"     entry_count={snap.entry_count}")
    print(f"     merkle_root={snap.merkle_root}")
    print(f"     by_entity={snap.by_entity}")
    print(f"     -> s3://{SNAPSHOT_BUCKET}/{LIBRARY_VERSION}/snapshot.json")

    print("\n== Stage 5: DATA-PLAN §5.4 acceptance ==")
    coverage_pass = len(entries) >= 50
    # Re-run validator on every entry (sanity check).
    recheck_failures = []
    for e in entries:
        passes, reasons = validate_entry(e, span_hash_universe)
        if not passes:
            recheck_failures.append({"entry_id": e.entry_id, "reasons": reasons})
    validator_pass = not recheck_failures

    # Snapshot integrity.
    reload = lib.load_snapshot(LIBRARY_VERSION)
    integrity_pass = reload.merkle_root == snap.merkle_root and reload.entry_count == snap.entry_count

    # Bootstrap tag enforcement.
    untagged = [e.entry_id for e in entries if "bootstrap" not in e.tags]
    tag_pass = not untagged

    # Replay test (DATA-PLAN §5.4 #3) — deferred to L01 audit which doesn't exist yet.

    flag = lambda b: "PASS" if b else "FAIL"
    print(f"  AC#1 ≥50 entries seeded                       : {flag(coverage_pass)}  ({len(entries)})")
    print(f"  AC#2 every entry passes L02 validator         : {flag(validator_pass)}  ({len(entries) - len(recheck_failures)}/{len(entries)})")
    print(f"  AC#3 replay test (deferred — needs L01 audit) : n/a")
    print(f"  AC#4 every entry tagged 'bootstrap'           : {flag(tag_pass)}  ({len(entries) - len(untagged)}/{len(entries)})")
    print(f"  + snapshot integrity (Merkle re-load)         : {flag(integrity_pass)}")

    report = {
        "version": LIBRARY_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "merkle_root": snap.merkle_root,
        "signed_by": snap.signed_by,
        "entry_count": snap.entry_count,
        "by_entity": snap.by_entity,
        "by_top_level": by_top,
        "candidates_scored": len(scored),
        "validator_failures": failures,
        "acceptance": {
            "ac1_coverage": coverage_pass,
            "ac2_validator": validator_pass,
            "ac3_replay": "deferred (L01 audit not yet built)",
            "ac4_bootstrap_tag": tag_pass,
            "snapshot_integrity": integrity_pass,
        },
    }
    out_path = MANIFESTS_DIR / "library-v0.1-report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nreport: {out_path.relative_to(REPO_ROOT)}")

    overall = coverage_pass and validator_pass and tag_pass and integrity_pass
    print(f"\noverall: {flag(overall)}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
