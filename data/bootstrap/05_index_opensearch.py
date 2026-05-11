#!/usr/bin/env python3
"""
DATA-PLAN.md §8 Day 6 — Lexical (BM25) index of evidence spans.

Creates the `spans-v1` index in OpenSearch with a custom DDQ analyzer:
  - Standard tokenizer
  - Lowercase + ASCII folding (for "AFME-IS-3.4" → "afme-is-3.4")
  - Light synonym filter seeded with DDQ vocabulary stand-ins (ddq.md §2
    "BM25, custom analyzers"). Real synonym set will come from SME work.

Loads `data/manifests/spans-full.json` (13,466 spans across 7 sources),
flattens nested anchor / provenance fields into top-level filter fields
(source, form, framework, year, quarter, control_id, etc.), and bulk-indexes
with `_id = span_id` for idempotency.

Run from repo root:
    .venv/bin/python data/bootstrap/05_index_opensearch.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import MANIFESTS_DIR, REPO_ROOT, write_json  # noqa: E402

from opensearchpy import OpenSearch  # noqa: E402
from opensearchpy.helpers import bulk  # noqa: E402

INDEX = "spans-v1"
HOST = "http://localhost:9200"

# DDQ vocabulary synonyms — placeholder seed. Real set comes from L05 SME work.
# Comma-separated synonym groups; each line is one group.
DDQ_SYNONYMS = [
    "soc 2, soc2, aicpa tsc, trust services criteria",
    "iso 27001, iso27001, isms",
    "pci dss, pci-dss, pci",
    "nist 800-53, sp 800-53, sp800-53, 800-53",
    "bcp, business continuity, business continuity plan",
    "drp, disaster recovery, disaster recovery plan",
    "mfa, multi-factor authentication, multifactor authentication, two-factor authentication, 2fa",
    "rto, recovery time objective",
    "rpo, recovery point objective",
    "kyc, know your customer",
    "aml, anti-money laundering",
    "esg, environmental social governance",
    "sla, service level agreement",
    "kri, key risk indicator",
    "sme, subject matter expert",
    "rfp, request for proposal",
    "ddq, due diligence questionnaire",
    "caiq, consensus assessments initiative questionnaire",
    "ccm, cloud controls matrix",
    "csf, cybersecurity framework",
]


def index_settings() -> dict:
    return {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "filter": {
                        "ddq_synonyms": {
                            "type": "synonym",
                            "lenient": True,
                            "synonyms": DDQ_SYNONYMS,
                        },
                        "english_stop": {"type": "stop", "stopwords": "_english_"},
                    },
                    "analyzer": {
                        "ddq_text": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "asciifolding", "english_stop", "ddq_synonyms"],
                        },
                        # Search-time analyzer skips the synonym filter on
                        # already-expanded queries (avoids double-expansion).
                        "ddq_text_search": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "asciifolding", "english_stop"],
                        },
                    },
                },
            }
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "doc_id": {"type": "keyword"},
                "doc_hash": {"type": "keyword"},
                "section_id": {"type": "keyword"},
                "span_id": {"type": "keyword"},
                "span_hash": {"type": "keyword"},
                "text": {
                    "type": "text",
                    "analyzer": "ddq_text",
                    "search_analyzer": "ddq_text_search",
                },
                # Filter facets — populated by extracting from anchor/provenance.
                "source": {"type": "keyword"},
                "entity": {"type": "keyword"},
                "form": {"type": "keyword"},
                "framework": {"type": "keyword"},
                "year": {"type": "integer"},
                "quarter": {"type": "integer"},
                "filing_date": {"type": "date"},
                "effective_date": {"type": "date"},
                "control_id": {"type": "keyword"},
                "anchor_kind": {"type": "keyword"},
                "anchor_page": {"type": "integer"},
                "anchor_item": {"type": "keyword"},
                "anchor_path": {"type": "keyword"},
                # Verbatim copies of nested objects, kept as JSON strings for replay.
                "anchor_json": {"type": "keyword", "index": False},
                "provenance_json": {"type": "keyword", "index": False},
            },
        },
    }


def derive_facets(span: dict, doc_lookup: dict) -> dict:
    """Pull filter fields out of anchor + provenance + linked doc metadata."""
    out: dict = {}
    prov = span.get("provenance") or {}
    anchor = span.get("anchor") or {}
    out["source"] = prov.get("source") or ""
    extra = prov.get("extra") or {}

    # Anchor flatten.
    kind = anchor.get("kind")
    out["anchor_kind"] = kind
    if kind == "page":
        out["anchor_page"] = anchor.get("page")
    elif kind == "section":
        out["anchor_item"] = anchor.get("item")
    elif kind == "structural":
        out["anchor_path"] = anchor.get("path")

    # Per-source facets.
    if out["source"] == "edgar":
        out["entity"] = "bny-mellon-corp"
        out["form"] = extra.get("form")
        fd = extra.get("filing_date")
        if fd:
            out["filing_date"] = fd
            out["effective_date"] = fd
            try:
                out["year"] = int(fd[:4])
            except (TypeError, ValueError):
                pass
    elif out["source"] == "bny-ir":
        out["entity"] = "bny-mellon-corp"
        if extra.get("year"):
            out["year"] = extra["year"]
        if extra.get("quarter"):
            out["quarter"] = extra["quarter"]
        # Get effective_date from doc metadata.
        d = doc_lookup.get(span["doc_id"])
        if d and d.get("effective_date"):
            out["effective_date"] = d["effective_date"]
    elif out["source"] in ("nist_csf", "nist_800_53"):
        out["framework"] = "NIST_CSF_v2.0" if out["source"] == "nist_csf" else "NIST_SP800_53_rev5"
        out["control_id"] = anchor.get("path")
    elif out["source"] in ("caiq", "ccm"):
        out["framework"] = "CAIQ_v4.0.3" if out["source"] == "caiq" else "CCM_v4.0.12"
        out["control_id"] = anchor.get("path")
    elif out["source"] == "afme":
        out["framework"] = "AFME_2026"
        if extra.get("year"):
            out["year"] = extra["year"]
    return {k: v for k, v in out.items() if v not in (None, "", {})}


def to_doc(span: dict, doc_lookup: dict) -> dict:
    doc = {
        "doc_id": span["doc_id"],
        "doc_hash": span["doc_hash"],
        "section_id": span["section_id"],
        "span_id": span["span_id"],
        "span_hash": span["span_hash"],
        "text": span["text"],
        "anchor_json": json.dumps(span.get("anchor") or {}),
        "provenance_json": json.dumps(span.get("provenance") or {}),
    }
    doc.update(derive_facets(span, doc_lookup))
    return doc


def actions(spans: list[dict], doc_lookup: dict):
    for s in spans:
        yield {"_op_type": "index", "_index": INDEX, "_id": s["span_id"], "_source": to_doc(s, doc_lookup)}


def main() -> int:
    client = OpenSearch(HOST, request_timeout=60)
    ok = client.ping()
    print(f"opensearch ping: {ok}")
    if not ok:
        print("  is the container up? `docker compose -f infra/docker/docker-compose.yml up -d opensearch`")
        return 2

    # Drop + recreate (Day-6 idempotency; re-runs always start clean).
    if client.indices.exists(INDEX):
        client.indices.delete(INDEX)
        print(f"  dropped existing index: {INDEX}")
    client.indices.create(INDEX, body=index_settings())
    print(f"  created index: {INDEX}")

    # Load spans + doc lookup for facet enrichment.
    by_source = json.loads((MANIFESTS_DIR / "spans-full.json").read_text(encoding="utf-8"))
    docs = json.loads((MANIFESTS_DIR / "knowledge-documents.json").read_text(encoding="utf-8"))
    doc_lookup = {d["doc_id"]: d for d in docs}

    flat: list[dict] = []
    for spans in by_source.values():
        flat.extend(spans)
    print(f"  spans to index: {len(flat):,}")

    started = time.time()
    success, errors = bulk(
        client, actions(flat, doc_lookup),
        chunk_size=500, request_timeout=120, raise_on_error=False, raise_on_exception=False,
    )
    elapsed = time.time() - started
    print(f"  indexed: {success:,}  errors: {len(errors) if isinstance(errors, list) else errors}  in {elapsed:.1f}s")

    # Refresh + count.
    client.indices.refresh(INDEX)
    count = client.count(index=INDEX)["count"]
    print(f"  index count: {count:,}")

    # Aggregate by source for sanity.
    aggs = client.search(index=INDEX, size=0, body={
        "aggs": {
            "by_source": {"terms": {"field": "source", "size": 20}},
            "by_form": {"terms": {"field": "form", "size": 20}},
            "by_framework": {"terms": {"field": "framework", "size": 20}},
        },
    })
    print("\n== Distribution ==")
    for facet in ("by_source", "by_form", "by_framework"):
        buckets = aggs["aggregations"][facet]["buckets"]
        print(f"  {facet}:")
        for b in buckets:
            print(f"    {b['key']:<25}  {b['doc_count']:>6}")

    write_json(MANIFESTS_DIR / "opensearch-index-report.json", {
        "index": INDEX,
        "indexed": success,
        "errors": errors if isinstance(errors, int) else len(errors),
        "count": count,
        "elapsed_secs": round(elapsed, 2),
        "aggs": aggs["aggregations"],
    })
    return 0 if (isinstance(errors, list) and not errors) or (isinstance(errors, int) and errors == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
