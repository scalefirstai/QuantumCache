#!/usr/bin/env python3
"""
DATA-PLAN.md §6.4 #2 — eval harness.

Loads `evals/fixtures/v0/eval_set.json`, runs hybrid retrieval (BM25 + dense
+ RRF, k=60) over the live OpenSearch + Qdrant indexes, and computes:

  * recall@1, recall@10, MRR — for "pass" items where expected_evidence_spans
    is non-empty.
  * halt-path correctness — for "halt" items, top RRF score below
    HALT_RRF_THRESHOLD = the validator-stub would refuse evidence as
    insufficient (citation guardrail halts).

The other §6.3 metrics (L05 mapping precision, L06 hallucination rate)
require services not yet built (TaxonomyService.classify_new_question +
DraftComposer); marked "deferred".

Output: `evals/reports/v0-baseline.json` plus a CI-style summary on stdout.

Run from repo root:
    .venv/bin/python evals/runners/run_eval_v0.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "data" / "bootstrap"))

from _lib import MANIFESTS_DIR  # noqa: E402

import torch  # noqa: E402
from opensearchpy import OpenSearch  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

FIXTURES = REPO_ROOT / "evals" / "fixtures" / "v0" / "eval_set.json"
REPORTS_DIR = REPO_ROOT / "evals" / "reports"

OS_HOST = "http://localhost:9200"
OS_INDEX = "spans-v1"
QDRANT_HOST = "http://localhost:6333"
QDRANT_COLL = "spans_v1"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
TOP_N = 30
TOP_K = 10
RRF_K = 60
HALT_RRF_THRESHOLD = 0.018      # ~ rank 5 in a single ranking; below this we'd halt


from qdrant_client.http import models as qm  # noqa: E402

# The eval question is "can we answer this DDQ question from BNY's public
# corpus?" — so retrieval is filtered to source ∈ {edgar, bny-ir}. Without
# this filter, the framework-source spans (AFME/CAIQ that encode the question
# itself) trivially top the rankings and recall@10 collapses to 0.
BNY_SOURCES = ("edgar", "bny-ir")


def bm25_search(client, query: str, n: int) -> list[dict]:
    body = {
        "size": n,
        "query": {
            "bool": {
                "must": [{"match": {"text": {"query": query, "operator": "or"}}}],
                "filter": [{"terms": {"source": list(BNY_SOURCES)}}],
            }
        },
        "_source": ["doc_id", "span_id", "span_hash", "source", "form", "anchor_kind",
                    "anchor_page", "anchor_item"],
    }
    resp = client.search(index=OS_INDEX, body=body)
    return [
        {"span_id": h["_source"]["span_id"], "span_hash": h["_source"]["span_hash"],
         "source": h["_source"]["source"], "score": h["_score"]}
        for h in resp["hits"]["hits"]
    ]


def dense_search(qdrant, model, query: str, n: int) -> list[dict]:
    vec = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
    qfilter = qm.Filter(should=[
        qm.FieldCondition(key="source", match=qm.MatchValue(value=src)) for src in BNY_SOURCES
    ])
    res = qdrant.query_points(
        collection_name=QDRANT_COLL, query=vec.tolist(), limit=n,
        query_filter=qfilter, with_payload=True,
    ).points
    return [
        {"span_id": (p.payload or {}).get("span_id"),
         "span_hash": (p.payload or {}).get("span_hash"),
         "source": (p.payload or {}).get("source"),
         "score": p.score}
        for p in res
    ]


def rrf(rankings, k=RRF_K, top_k=TOP_K):
    scores = defaultdict(float)
    record = {}
    for hits in rankings:
        for rank, h in enumerate(hits):
            sid = h["span_id"]
            scores[sid] += 1.0 / (k + rank + 1)
            record.setdefault(sid, h)
    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return [{**record[sid], "rrf_score": sc} for sid, sc in fused]


def evaluate_item(item: dict, os_client, qdrant, model) -> dict:
    query = item["raw_question_text"]
    bm = bm25_search(os_client, query, TOP_N)
    dn = dense_search(qdrant, model, query, TOP_N)
    fu = rrf([bm, dn])
    expected_hashes = {s["span_hash"] for s in item.get("expected_evidence_spans", [])}
    retrieved_hashes = [h["span_hash"] for h in fu]
    expected_doc_ids = {s.get("doc_id") for s in item.get("expected_evidence_spans", []) if s.get("doc_id")}
    retrieved_doc_ids_top10 = [h.get("doc_id") for h in fu[:TOP_K]]  # populated only if payload had doc_id

    # hit metrics — span_hash equality (DATA-PLAN §6.4 wants hashes pinned).
    hit_at_1 = bool(expected_hashes) and (retrieved_hashes[0] in expected_hashes if retrieved_hashes else False)
    hit_at_10 = bool(expected_hashes) and any(h in expected_hashes for h in retrieved_hashes[:TOP_K])
    rank = next((i + 1 for i, h in enumerate(retrieved_hashes[:TOP_K]) if h in expected_hashes), None)
    rr = (1.0 / rank) if rank else 0.0

    top_score = fu[0]["rrf_score"] if fu else 0.0
    halt_signal = top_score < HALT_RRF_THRESHOLD

    return {
        "eval_id": item["eval_id"],
        "framework": item["framework"],
        "expected_verdict": item["expected_verdict"],
        "top_score": top_score,
        "halt_signal": halt_signal,
        "hit_at_1": hit_at_1,
        "hit_at_10": hit_at_10,
        "rank_of_first_hit": rank,
        "reciprocal_rank": rr,
        "retrieved_top_3_sources": [h.get("source") for h in fu[:3]],
    }


def aggregate(results: list[dict]) -> dict:
    by_slice: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_slice[r["framework"]].append(r)

    metrics: dict = {}
    for slice_name, recs in by_slice.items():
        passes = [r for r in recs if r["expected_verdict"] == "pass"]
        halts = [r for r in recs if r["expected_verdict"] == "halt"]
        m: dict = {"count": len(recs), "pass_count": len(passes), "halt_count": len(halts)}
        if passes:
            m["recall_at_1"] = sum(1 for r in passes if r["hit_at_1"]) / len(passes)
            m["recall_at_10"] = sum(1 for r in passes if r["hit_at_10"]) / len(passes)
            m["mrr"] = sum(r["reciprocal_rank"] for r in passes) / len(passes)
        if halts:
            m["halt_rate"] = sum(1 for r in halts if r["halt_signal"]) / len(halts)
        metrics[slice_name] = m

    overall_pass = [r for r in results if r["expected_verdict"] == "pass"]
    overall_halt = [r for r in results if r["expected_verdict"] == "halt"]
    overall = {
        "total": len(results),
        "pass_items": len(overall_pass),
        "halt_items": len(overall_halt),
        "recall_at_1": sum(1 for r in overall_pass if r["hit_at_1"]) / len(overall_pass) if overall_pass else None,
        "recall_at_10": sum(1 for r in overall_pass if r["hit_at_10"]) / len(overall_pass) if overall_pass else None,
        "mrr": sum(r["reciprocal_rank"] for r in overall_pass) / len(overall_pass) if overall_pass else None,
        "halt_rate": sum(1 for r in overall_halt if r["halt_signal"]) / len(overall_halt) if overall_halt else None,
    }
    return {"by_slice": metrics, "overall": overall}


def main() -> int:
    print(f"== loading fixtures from {FIXTURES.relative_to(REPO_ROOT)}")
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    items = fixtures["items"]
    print(f"  items: {len(items)}  corpus_pin: {fixtures['corpus_pin']}")

    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(MODEL_NAME, device=device)
    model.max_seq_length = 384
    os_client = OpenSearch(OS_HOST, request_timeout=60)
    qdrant = QdrantClient(url=QDRANT_HOST, timeout=60)

    print(f"\n== running {len(items)} items ==")
    t0 = time.time()
    results: list[dict] = []
    for i, item in enumerate(items, start=1):
        results.append(evaluate_item(item, os_client, qdrant, model))
        if i % 25 == 0:
            print(f"   {i}/{len(items)}  ({time.time()-t0:.1f}s)")
    print(f"   done  ({time.time()-t0:.1f}s)")

    metrics = aggregate(results)
    print("\n== Metrics by slice ==")
    for slice_name in ("AFME", "CAIQ", "AFME_ESG", "ADVERSARIAL", "ADV"):
        m = metrics["by_slice"].get(slice_name, {})
        if not m:
            continue
        line = f"  {slice_name:<13} n={m['count']:>3}"
        if "recall_at_10" in m:
            line += f"  recall@10={m['recall_at_10']:.2%}  recall@1={m['recall_at_1']:.2%}  MRR={m['mrr']:.3f}"
        if "halt_rate" in m:
            line += f"  halt_rate={m['halt_rate']:.2%}"
        print(line)
    print()
    o = metrics["overall"]
    print(f"  OVERALL pass items={o['pass_items']}  recall@10={o['recall_at_10']:.2%}  MRR={o['mrr']:.3f}")
    print(f"          halt items={o['halt_items']}  halt_rate={o['halt_rate']:.2%}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "v0-baseline.json"
    out_path.write_text(json.dumps({
        "version": "v0",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "corpus_pin": fixtures["corpus_pin"],
        "halt_rrf_threshold": HALT_RRF_THRESHOLD,
        "metrics": metrics,
        "deferred": ["L05 mapping precision (TaxonomyService.classify_new_question — M1)",
                     "L06 hallucination rate (DraftComposer — M3)"],
        "per_item": results,
    }, indent=2), encoding="utf-8")
    print(f"\nbaseline: {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
