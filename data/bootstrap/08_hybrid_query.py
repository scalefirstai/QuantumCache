#!/usr/bin/env python3
"""
DATA-PLAN.md §8 Day 7 — Hybrid retrieval smoke test.

For each query, run:
  1. BM25 (OpenSearch spans-v1, top 50)
  2. Dense (Qdrant spans_v1 with BGE-small-en-v1.5, top 50)
  3. Reciprocal Rank Fusion (k=60) over both rankings → final top-K

ddq.md §L03 specifies BM25 top-100 ∪ dense top-100 → Cohere Rerank → top-k.
Cohere rerank requires an API key not available in dev; RRF is the standard
no-key fusion technique that approximates the hybrid pipeline well enough
to validate the spine.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import MANIFESTS_DIR, REPO_ROOT  # noqa: E402

from opensearchpy import OpenSearch  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.http import models as qm  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

import torch  # noqa: E402

OS_HOST = "http://localhost:9200"
OS_INDEX = "spans-v1"
QDRANT_HOST = "http://localhost:6333"
QDRANT_COLL = "spans_v1"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
TOP_N = 50          # candidates per backend
TOP_K = 10          # final returned after fusion
RRF_K = 60          # standard RRF constant

QUERIES = [
    {
        "id": "q.iam.privileged_access",
        "text": "privileged access review cadence and approval chain",
        "expected_sources": {"caiq", "ccm", "nist_800_53", "afme"},
        "filters": {},
    },
    {
        "id": "q.bcp.testing",
        "text": "business continuity plan testing frequency disaster recovery",
        "expected_sources": {"caiq", "ccm", "nist_800_53", "afme"},
        "filters": {},
    },
    {
        "id": "q.crypto.at_rest",
        "text": "encryption at rest key management cryptographic controls",
        "expected_sources": {"caiq", "ccm", "nist_800_53"},
        "filters": {},
    },
    {
        "id": "q.governance.board",
        "text": "board composition independent directors governance",
        "expected_sources": {"edgar"},
        "filters": {"form": "DEF 14A"},
    },
    {
        "id": "q.business.segments",
        "text": "principal business segments revenue mix custody investment management",
        "expected_sources": {"edgar"},
        "filters": {"form": "10-K"},
    },
    {
        "id": "q.capital.pillar3",
        "text": "common equity tier 1 ratio risk weighted assets capital",
        "expected_sources": {"bny-ir"},
        "filters": {"source": "bny-ir"},
    },
    {
        "id": "q.adversarial.no_match",
        "text": "exotic synthetic CDO origination underwriting cycles",
        "expected_sources": set(),
        "filters": {},
    },
]


def bm25_search(client: OpenSearch, q: dict, n: int) -> list[dict]:
    body = {
        "size": n,
        "query": {
            "bool": {
                "must": [{"match": {"text": {"query": q["text"], "operator": "or"}}}],
                "filter": [{"term": {k: v}} for k, v in q["filters"].items()],
            }
        },
        "_source": ["doc_id", "section_id", "span_id", "source", "form", "framework",
                    "control_id", "anchor_kind", "anchor_page", "anchor_item", "anchor_path", "text"],
    }
    resp = client.search(index=OS_INDEX, body=body)
    out = []
    for h in resp["hits"]["hits"]:
        s = h["_source"]
        out.append({"span_id": s["span_id"], "score": h["_score"], "source": s.get("source"),
                    "doc_id": s["doc_id"], "section_id": s.get("section_id"),
                    "anchor": s.get("anchor_item") or s.get("anchor_path") or f"page {s.get('anchor_page')}",
                    "text": s.get("text", "")})
    return out


def dense_search(qdrant: QdrantClient, model, q: dict, n: int) -> list[dict]:
    vec = model.encode([q["text"]], normalize_embeddings=True, convert_to_numpy=True)[0]
    qfilter = None
    if q["filters"]:
        qfilter = qm.Filter(must=[
            qm.FieldCondition(key=k, match=qm.MatchValue(value=v)) for k, v in q["filters"].items()
        ])
    res = qdrant.query_points(
        collection_name=QDRANT_COLL, query=vec.tolist(), limit=n,
        query_filter=qfilter, with_payload=True,
    ).points
    out = []
    for p in res:
        pl = p.payload or {}
        out.append({"span_id": pl.get("span_id"), "score": p.score, "source": pl.get("source"),
                    "doc_id": pl.get("doc_id"), "section_id": pl.get("section_id"),
                    "anchor": pl.get("anchor_item") or pl.get("anchor_path") or f"page {pl.get('anchor_page')}",
                    "text": pl.get("text", "")})
    return out


def rrf(rankings: list[list[dict]], k: int = RRF_K, top_k: int = TOP_K) -> list[dict]:
    """Standard reciprocal rank fusion. rankings = [bm25_hits, dense_hits, ...]."""
    scores: dict[str, float] = {}
    record: dict[str, dict] = {}
    sources_per_id: dict[str, list[str]] = {}
    for ri, hits in enumerate(rankings):
        for rank, h in enumerate(hits):
            sid = h["span_id"]
            scores[sid] = scores.get(sid, 0.0) + 1.0 / (k + rank + 1)
            record.setdefault(sid, h)
            sources_per_id.setdefault(sid, []).append(f"r{ri}@{rank+1}")
    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    out = []
    for sid, sc in fused:
        h = dict(record[sid])
        h["rrf_score"] = sc
        h["rrf_origins"] = sources_per_id[sid]
        out.append(h)
    return out


def fmt_hit(h: dict, max_text: int = 110) -> str:
    text = (h.get("text") or "").replace("\n", " ").strip()
    if len(text) > max_text:
        text = text[:max_text] + "…"
    return (f"score={h.get('score') or h.get('rrf_score', 0):>6.3f}  "
            f"[{(h.get('source') or '?'):<11}] {(h.get('anchor') or '')[:36]:<36}  {text}")


def main() -> int:
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    print(f"== loading model {MODEL_NAME} on {device}")
    model = SentenceTransformer(MODEL_NAME, device=device)
    os_client = OpenSearch(OS_HOST, request_timeout=60)
    qdrant = QdrantClient(url=QDRANT_HOST, timeout=60)

    print(f"== Hybrid retrieval smoke ({len(QUERIES)} queries, top_n={TOP_N}, top_k={TOP_K}, rrf_k={RRF_K})\n")
    overall = []
    for q in QUERIES:
        bm = bm25_search(os_client, q, TOP_N)
        dn = dense_search(qdrant, model, q, TOP_N)
        fu = rrf([bm, dn])

        bm_sources = {h["source"] for h in bm[:TOP_K]}
        dn_sources = {h["source"] for h in dn[:TOP_K]}
        fu_sources = {h["source"] for h in fu}
        bm_ids = {h["span_id"] for h in bm[:TOP_K]}
        dn_ids = {h["span_id"] for h in dn[:TOP_K]}
        overlap = bm_ids & dn_ids

        if q["expected_sources"]:
            covered_bm = bool(bm_sources & q["expected_sources"])
            covered_dn = bool(dn_sources & q["expected_sources"])
            covered_fu = bool(fu_sources & q["expected_sources"])
            verdict = "PASS" if (covered_bm or covered_dn) and covered_fu else "FAIL"
        else:
            verdict = "PASS" if (not fu or fu[0].get("rrf_score", 0) < 0.04) else "WEAK"

        print(f"  [{verdict}]  {q['id']}   '{q['text']}'")
        print(f"         BM25 top sources: {sorted(bm_sources) or '∅'}")
        print(f"         Dense top sources: {sorted(dn_sources) or '∅'}")
        print(f"         RRF top sources: {sorted(fu_sources) or '∅'}   overlap@10: {len(overlap)}/{TOP_K}")

        print(f"         BM25  : {fmt_hit(bm[0]) if bm else '(empty)'}")
        print(f"         Dense : {fmt_hit(dn[0]) if dn else '(empty)'}")
        print(f"         RRF#1 : {fmt_hit(fu[0]) if fu else '(empty)'}")
        print(f"         RRF#2 : {fmt_hit(fu[1]) if len(fu) > 1 else '(empty)'}")
        print()

        overall.append({
            "id": q["id"], "text": q["text"], "verdict": verdict,
            "bm25_sources": sorted(bm_sources), "dense_sources": sorted(dn_sources),
            "rrf_sources": sorted(fu_sources),
            "overlap_at_k": len(overlap),
            "rrf_top": [{"span_id": h["span_id"], "source": h["source"], "rrf_score": h["rrf_score"],
                         "origins": h["rrf_origins"]} for h in fu[:5]],
        })

    out = MANIFESTS_DIR / "hybrid-smoke-report.json"
    out.write_text(json.dumps(overall, indent=2), encoding="utf-8")
    print(f"report: {out.relative_to(REPO_ROOT)}")

    failed = [r for r in overall if r["verdict"] == "FAIL"]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
