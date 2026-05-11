#!/usr/bin/env python3
"""
DATA-PLAN.md §8 Day 7 — Dense vector index of evidence spans.

Embeds the 13,466 spans with `BAAI/bge-small-en-v1.5` (384-dim) and upserts
into Qdrant collection `spans_v1` with the same filter payload that
OpenSearch already carries. Production path swaps in Bedrock Titan via the
LLMClient interface (ddq.md §L06); for local dev sentence-transformers is
the no-network fallback.

`point_id` is a deterministic uint64 derived from `span_id` so re-runs are
idempotent. Filter payload mirrors OpenSearch facets so a future
HybridRetrieval port can issue the same filter dict to both backends.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import MANIFESTS_DIR, REPO_ROOT, write_json  # noqa: E402

from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.http import models as qm  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

import torch  # noqa: E402

COLLECTION = "spans_v1"
HOST = "http://localhost:6333"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
VECTOR_DIM = 384
BATCH = 16        # MPS unified-memory ceiling on 16 GB Macs is tight at batch=64
MAX_SEQ_LEN = 384 # truncate to keep single-batch memory bounded


def point_id_for(span_id: str) -> int:
    """Deterministic uint64 from a span_id string."""
    return int.from_bytes(hashlib.sha1(span_id.encode("utf-8")).digest()[:8], "big")


def derive_payload(span: dict, doc_lookup: dict) -> dict:
    """Mirror the OpenSearch facet derivation so filters match across backends."""
    prov = span.get("provenance") or {}
    anchor = span.get("anchor") or {}
    extra = prov.get("extra") or {}
    payload: dict = {
        "doc_id": span["doc_id"],
        "doc_hash": span["doc_hash"],
        "section_id": span["section_id"],
        "span_id": span["span_id"],
        "span_hash": span["span_hash"],
        "source": prov.get("source"),
        "anchor_kind": anchor.get("kind"),
    }
    if anchor.get("kind") == "page":
        payload["anchor_page"] = anchor.get("page")
    elif anchor.get("kind") == "section":
        payload["anchor_item"] = anchor.get("item")
    elif anchor.get("kind") == "structural":
        payload["anchor_path"] = anchor.get("path")

    src = payload["source"]
    if src == "edgar":
        payload["entity"] = "bny-mellon-corp"
        payload["form"] = extra.get("form")
        if extra.get("filing_date"):
            payload["filing_date"] = extra["filing_date"]
            payload["effective_date"] = extra["filing_date"]
            try:
                payload["year"] = int(extra["filing_date"][:4])
            except (TypeError, ValueError):
                pass
    elif src == "bny-ir":
        payload["entity"] = "bny-mellon-corp"
        if extra.get("year"):
            payload["year"] = extra["year"]
        if extra.get("quarter"):
            payload["quarter"] = extra["quarter"]
        d = doc_lookup.get(span["doc_id"])
        if d and d.get("effective_date"):
            payload["effective_date"] = d["effective_date"]
    elif src in ("nist_csf", "nist_800_53"):
        payload["framework"] = "NIST_CSF_v2.0" if src == "nist_csf" else "NIST_SP800_53_rev5"
        payload["control_id"] = anchor.get("path")
    elif src in ("caiq", "ccm"):
        payload["framework"] = "CAIQ_v4.0.3" if src == "caiq" else "CCM_v4.0.12"
        payload["control_id"] = anchor.get("path")
    elif src == "afme":
        payload["framework"] = "AFME_2026"
        if extra.get("year"):
            payload["year"] = extra["year"]
    return {k: v for k, v in payload.items() if v not in (None, "", {})}


def main() -> int:
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    print(f"== loading model {MODEL_NAME} on {device}")
    t0 = time.time()
    model = SentenceTransformer(MODEL_NAME, device=device)
    model.max_seq_length = MAX_SEQ_LEN
    print(f"   loaded in {time.time() - t0:.1f}s  max_seq_len={model.max_seq_length}")

    by_source = json.loads((MANIFESTS_DIR / "spans-full.json").read_text(encoding="utf-8"))
    docs = json.loads((MANIFESTS_DIR / "knowledge-documents.json").read_text(encoding="utf-8"))
    doc_lookup = {d["doc_id"]: d for d in docs}

    flat: list[dict] = []
    for spans in by_source.values():
        flat.extend(spans)
    print(f"== spans to embed: {len(flat):,}")

    qdrant = QdrantClient(url=HOST, timeout=120)
    if qdrant.collection_exists(COLLECTION):
        qdrant.delete_collection(COLLECTION)
        print(f"   dropped collection: {COLLECTION}")
    qdrant.create_collection(
        collection_name=COLLECTION,
        vectors_config=qm.VectorParams(size=VECTOR_DIM, distance=qm.Distance.COSINE),
        # Performance tuning: HNSW defaults are fine for 13K vectors.
        on_disk_payload=False,
    )
    # Index payload fields we'll filter on (faster term/range queries).
    for field in ("source", "entity", "form", "framework", "control_id", "anchor_kind"):
        qdrant.create_payload_index(COLLECTION, field_name=field, field_schema=qm.PayloadSchemaType.KEYWORD)
    for field in ("year", "quarter", "anchor_page"):
        qdrant.create_payload_index(COLLECTION, field_name=field, field_schema=qm.PayloadSchemaType.INTEGER)
    print(f"   created collection: {COLLECTION}  dim={VECTOR_DIM}  cosine")

    t1 = time.time()
    pending: list[qm.PointStruct] = []
    upserted = 0
    BATCH_UPSERT = 256
    for i in range(0, len(flat), BATCH):
        chunk = flat[i:i + BATCH]
        texts = [s["text"] for s in chunk]
        embeddings = model.encode(
            texts, batch_size=BATCH, normalize_embeddings=True,
            show_progress_bar=False, convert_to_numpy=True,
        )
        for span, vec in zip(chunk, embeddings):
            pending.append(qm.PointStruct(
                id=point_id_for(span["span_id"]),
                vector=vec.tolist(),
                payload={**derive_payload(span, doc_lookup), "text": span["text"]},
            ))
        if len(pending) >= BATCH_UPSERT:
            qdrant.upsert(collection_name=COLLECTION, points=pending, wait=False)
            upserted += len(pending)
            pending = []
            elapsed = time.time() - t1
            rate = upserted / elapsed if elapsed > 0 else 0
            eta = (len(flat) - upserted) / rate if rate > 0 else 0
            print(f"   upserted {upserted:>6,}/{len(flat):,}  ({rate:>6.0f}/s  eta {eta:>4.0f}s)")
    if pending:
        qdrant.upsert(collection_name=COLLECTION, points=pending, wait=True)
        upserted += len(pending)
    print(f"   total upserted: {upserted:,}  in {time.time() - t1:.1f}s")

    # Final count.
    info = qdrant.get_collection(COLLECTION)
    actual_count = info.points_count
    print(f"\n== qdrant collection {COLLECTION}: {actual_count:,} points")

    write_json(MANIFESTS_DIR / "qdrant-index-report.json", {
        "collection": COLLECTION,
        "model": MODEL_NAME,
        "vector_dim": VECTOR_DIM,
        "device": device,
        "spans": len(flat),
        "upserted": upserted,
        "points_in_collection": actual_count,
        "elapsed_secs": round(time.time() - t1, 2),
    })
    return 0 if actual_count == len(flat) else 1


if __name__ == "__main__":
    raise SystemExit(main())
