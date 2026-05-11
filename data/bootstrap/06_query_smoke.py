#!/usr/bin/env python3
"""
DATA-PLAN.md §8 Day 6 — BM25 smoke test.

Runs realistic DDQ queries against the spans-v1 OpenSearch index and checks
that hits land in the sources we'd expect. This is not yet a recall@k
measurement (no eval set until Day 12); it's a "the index isn't broken,
analyzer is sane, filters work" smoke check.

Each query has:
  - text:             free-text question
  - expected_sources: sources that SHOULD have hits in the top-k
  - filters:          OPA-style filter dict (becomes OpenSearch term filters)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import MANIFESTS_DIR, REPO_ROOT  # noqa: E402

from opensearchpy import OpenSearch  # noqa: E402

INDEX = "spans-v1"
HOST = "http://localhost:9200"

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
        "expected_sources": set(),       # adversarial — could be empty / weak
        "filters": {},
    },
]

K = 10


def build_query(q: dict) -> dict:
    must = {"match": {"text": {"query": q["text"], "operator": "or"}}}
    filters = []
    for k, v in q["filters"].items():
        filters.append({"term": {k: v}})
    return {
        "size": K,
        "query": {"bool": {"must": [must], "filter": filters}},
        "_source": ["doc_id", "section_id", "span_id", "source", "form", "framework",
                    "control_id", "filing_date", "anchor_kind", "anchor_page", "anchor_item"],
        "highlight": {"fields": {"text": {"fragment_size": 160, "number_of_fragments": 1}}},
    }


def main() -> int:
    client = OpenSearch(HOST, request_timeout=60)
    if not client.ping():
        print("opensearch not reachable", file=sys.stderr)
        return 2

    print(f"== BM25 smoke ({len(QUERIES)} queries, k={K}) ==\n")
    overall_results: list[dict] = []
    for q in QUERIES:
        body = build_query(q)
        resp = client.search(index=INDEX, body=body)
        hits = resp["hits"]["hits"]
        sources_seen = {h["_source"].get("source", "?") for h in hits}
        expected = q["expected_sources"]
        # For adversarial query, expected is empty set (we want "weak signal" — a few hits is OK).
        if expected:
            covered = expected & sources_seen
            verdict = "PASS" if covered else "FAIL"
        else:
            # Adversarial: PASS if either no hits OR all top scores are low (<5).
            verdict = "PASS" if not hits or hits[0]["_score"] < 5.0 else "WEAK"

        print(f"  [{verdict:<4}] {q['id']:<30}  '{q['text'][:55]}'")
        print(f"         sources hit: {sorted(sources_seen) or '∅'}  expected: {sorted(expected) or '∅'}")
        for i, h in enumerate(hits[:3], start=1):
            src = h["_source"]
            highlight = (h.get("highlight", {}).get("text") or [""])[0]
            anchor = src.get("anchor_item") or src.get("anchor_path") or f"page {src.get('anchor_page')}"
            print(f"         {i}. score={h['_score']:6.2f}  [{src.get('source','?'):<11}] {anchor[:40]:<40}")
            if highlight:
                # Strip HTML em tags for readability.
                clean = highlight.replace("<em>", "**").replace("</em>", "**")
                print(f"             {clean[:140]}")
        print()
        overall_results.append({
            "id": q["id"], "text": q["text"], "expected_sources": sorted(expected),
            "sources_seen": sorted(sources_seen), "verdict": verdict,
            "top_score": hits[0]["_score"] if hits else 0.0,
            "top_3": [{"score": h["_score"], "source": h["_source"].get("source"),
                      "doc_id": h["_source"].get("doc_id"), "span_id": h["_id"]} for h in hits[:3]],
        })

    out = MANIFESTS_DIR / "bm25-smoke-report.json"
    out.write_text(json.dumps(overall_results, indent=2), encoding="utf-8")
    print(f"\nreport: {out.relative_to(REPO_ROOT)}")
    failed = [r for r in overall_results if r["verdict"] == "FAIL"]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
