#!/usr/bin/env python3
"""
DATA-PLAN.md §8 Day 5-7 (parse phase): turn ingested raw bytes into the
(doc_id, section_id, span_id, text, anchor, hash) tuples that ddq.md §L03
indexes against.

Inputs:
  - data/manifests/knowledge-documents.json  (BNY corpus from Day 3-4)
  - framework artifacts under data/sources/  (CAIQ, CCM, NIST OSCAL, AFME)

For each doc, route bytes to the right parser. Bodies are pulled from S3
(LocalStack) for EDGAR + BNY IR, from local disk for framework sources.

Output:
  - data/manifests/spans.json                (full tuple list, per-doc summary)
  - s3://bny-ddq-knowledge-parquet/year=YYYY/month=MM/source=<src>/spans.parquet
    (one parquet per source, partitioned by ingest year/month)
  - data/manifests/parse-acceptance.json     (round-trip + hash checks)
"""

from __future__ import annotations

import datetime as dt
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import (  # noqa: E402
    MANIFESTS_DIR,
    REPO_ROOT,
    S3_KNOWLEDGE_RAW,
    SOURCES_DIR,
    s3_client,
    write_json,
)
from parsers import caiq_json, docx_parse, edgar_html, pdf_pymupdf  # noqa: E402

S3_PARQUET = "bny-ddq-knowledge-parquet"


def fetch_s3_bytes(s3, uri: str) -> bytes:
    bucket, key = uri.removeprefix("s3://").split("/", 1)
    obj = s3.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read()


def fetch_local_bytes(rel_path: str) -> tuple[bytes, str]:
    p = REPO_ROOT / rel_path
    body = p.read_bytes()
    import hashlib
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    return body, digest


def framework_documents() -> list[dict]:
    """Hand-rolled list of framework docs to parse. Doc hashes computed on read.

    These aren't in knowledge-documents.json because they aren't part of the
    BNY corpus — they're the canonical taxonomy seed material.
    """
    return [
        {
            "doc_id": "caiq:v4.0.3:primary-dataset",
            "kind": "caiq_questions",
            "source": "caiq",
            "rel_path": "data/sources/caiq/_extracted/ccm-machine-readable-bundle/CCMv4.0.12+CAIQv4.0.3-JSON-Dataset_Generated-at_2024-06-03/CAIQ/primary-dataset.json",
        },
        {
            "doc_id": "ccm:v4.0.12:primary-dataset",
            "kind": "ccm_controls",
            "source": "ccm",
            "rel_path": "data/sources/caiq/_extracted/ccm-machine-readable-bundle/CCMv4.0.12+CAIQv4.0.3-JSON-Dataset_Generated-at_2024-06-03/CCM/primary-dataset.json",
        },
        {
            "doc_id": "nist:csf:v2.0:catalog",
            "kind": "oscal_catalog",
            "source": "nist_csf",
            "framework": "NIST_CSF_v2.0",
            "rel_path": "data/sources/nist/NIST_CSF_v2.0_catalog.json",
        },
        {
            "doc_id": "nist:sp800-53:rev5:catalog",
            "kind": "oscal_catalog",
            "source": "nist_800_53",
            "framework": "NIST_SP800_53_rev5",
            "rel_path": "data/sources/nist/NIST_SP-800-53_rev5_catalog.json",
        },
        {
            "doc_id": "afme:ddq-custodian:2026",
            "kind": "docx",
            "source": "afme",
            "rel_path": "data/sources/afme/afme-ddq-custodian-2026.docx",
            "extra": {"variant": "custodian", "year": 2026},
        },
        {
            "doc_id": "afme:ddq-csd:2026",
            "kind": "docx",
            "source": "afme",
            "rel_path": "data/sources/afme/afme-ddq-csd-2026.docx",
            "extra": {"variant": "csd", "year": 2026},
        },
        {
            "doc_id": "afme:ddq-prime-broker:2026",
            "kind": "docx",
            "source": "afme",
            "rel_path": "data/sources/afme/afme-ddq-prime-broker-2026.docx",
            "extra": {"variant": "prime_broker", "year": 2026},
        },
        {
            "doc_id": "afme:hy-esg:2026",
            "kind": "pdf",
            "source": "afme",
            "rel_path": "data/sources/afme/afme-hy-esg-2026.pdf",
            "extra": {"variant": "hy_esg", "year": 2026},
        },
    ]


def parse_doc(doc: dict, body: bytes, doc_hash: str) -> list[dict]:
    """Route doc to the right parser; return list of span dicts."""
    spans = []
    source = doc.get("source", "")
    if source == "edgar":
        for span in edgar_html.parse_edgar_html(
            body=body,
            doc_id=doc["doc_id"],
            doc_hash=doc_hash,
            form=doc["form"],
            filing_date=doc["filing_date"],
            accession=doc["accession"],
        ):
            spans.append(span.to_dict())
    elif source == "bny-ir":
        for span in pdf_pymupdf.parse_pdf(
            body=body, doc_id=doc["doc_id"], doc_hash=doc_hash, source="bny-ir",
            extra={
                "kind": doc.get("kind"),
                "year": doc.get("year"),
                "quarter": doc.get("quarter"),
            },
        ):
            spans.append(span.to_dict())
    elif source == "caiq":
        for span in caiq_json.parse_caiq_questions(
            body=body, doc_id=doc["doc_id"], doc_hash=doc_hash
        ):
            spans.append(span.to_dict())
    elif source == "ccm":
        for span in caiq_json.parse_ccm_controls(
            body=body, doc_id=doc["doc_id"], doc_hash=doc_hash
        ):
            spans.append(span.to_dict())
    elif source in ("nist_csf", "nist_800_53"):
        for span in caiq_json.parse_oscal_catalog(
            body=body, doc_id=doc["doc_id"], doc_hash=doc_hash,
            source=source, framework=doc["framework"]
        ):
            spans.append(span.to_dict())
    elif source == "afme":
        if doc["kind"] == "docx":
            for span in docx_parse.parse_docx(
                body=body, doc_id=doc["doc_id"], doc_hash=doc_hash, source="afme",
                extra=doc.get("extra"),
            ):
                spans.append(span.to_dict())
        elif doc["kind"] == "pdf":
            for span in pdf_pymupdf.parse_pdf(
                body=body, doc_id=doc["doc_id"], doc_hash=doc_hash, source="afme",
                extra=doc.get("extra"),
            ):
                spans.append(span.to_dict())
    else:
        print(f"  skip: unknown source for {doc.get('doc_id', '?')}: {source}")
    return spans


def write_parquet_to_s3(s3, source: str, spans: list[dict]) -> str:
    """Write spans grouped by source to parquet, upload to LocalStack."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    if not spans:
        return ""

    # pyarrow needs flat columns; serialize nested dicts as JSON strings.
    flat = []
    for s in spans:
        flat.append({
            "doc_id": s["doc_id"],
            "doc_hash": s["doc_hash"],
            "section_id": s["section_id"],
            "span_id": s["span_id"],
            "span_hash": s["span_hash"],
            "text": s["text"],
            "anchor_json": json.dumps(s["anchor"]),
            "provenance_json": json.dumps(s["provenance"]),
        })
    table = pa.Table.from_pylist(flat)
    buf = pa.BufferOutputStream()
    pq.write_table(table, buf, compression="zstd")
    parquet_bytes = buf.getvalue().to_pybytes()

    today = dt.date.today()
    key = f"year={today.year}/month={today.month:02d}/source={source}/spans.parquet"
    s3.put_object(
        Bucket=S3_PARQUET,
        Key=key,
        Body=parquet_bytes,
        ContentType="application/vnd.apache.parquet",
        Metadata={"source": source, "span_count": str(len(spans)), "bootstrap": "true"},
    )
    return f"s3://{S3_PARQUET}/{key}"


def main() -> int:
    s3 = s3_client()
    edgar_ir = json.loads((MANIFESTS_DIR / "knowledge-documents.json").read_text(encoding="utf-8"))
    fwks = framework_documents()

    print(f"== Parse  edgar+ir docs={len(edgar_ir)}  framework docs={len(fwks)}")

    by_source_spans: dict[str, list[dict]] = {}
    summary: list[dict] = []

    # ── EDGAR + BNY IR (S3-resident) ──────────────────────────────
    for i, d in enumerate(edgar_ir, start=1):
        doc_hash_raw = d["doc_hash"]  # already "sha256:<hex>"
        try:
            body = fetch_s3_bytes(s3, d["s3_uri"])
        except Exception as e:  # noqa: BLE001
            print(f"  [{i:>3}/{len(edgar_ir)}] s3 fetch failed: {d['doc_id']}: {e}")
            continue
        spans = parse_doc(d, body, doc_hash_raw)
        by_source_spans.setdefault(d["source"], []).extend(spans)
        summary.append({"doc_id": d["doc_id"], "source": d["source"], "spans": len(spans)})
        if i % 10 == 0 or i == len(edgar_ir):
            print(f"  [{i:>3}/{len(edgar_ir)}] {d['source']:<10} {d.get('form', d.get('kind',''))} -> {len(spans):>5} spans")

    # ── Framework sources (local disk) ────────────────────────────
    for d in fwks:
        try:
            body, doc_hash = fetch_local_bytes(d["rel_path"])
        except Exception as e:  # noqa: BLE001
            print(f"  framework: read failed: {d['doc_id']}: {e}")
            continue
        spans = parse_doc(d, body, doc_hash)
        by_source_spans.setdefault(d["source"], []).extend(spans)
        summary.append({"doc_id": d["doc_id"], "source": d["source"], "spans": len(spans)})
        print(f"  framework: {d['source']:<14}  {d['doc_id']:<35}  -> {len(spans):>5} spans")

    # ── Write parquet to S3 + summary to disk ─────────────────────
    print("\n== Writing parquet shadows to LocalStack ==")
    parquet_uris: dict[str, str] = {}
    total_spans = 0
    for src, spans in by_source_spans.items():
        uri = write_parquet_to_s3(s3, src, spans)
        parquet_uris[src] = uri
        total_spans += len(spans)
        print(f"  {src:<14}  {len(spans):>6} spans  -> {uri}")

    # Persist a JSON shadow too (cheaper to inspect/diff than parquet).
    shadow_path = MANIFESTS_DIR / "spans.json"
    shadow = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_spans": total_spans,
        "by_source": {k: len(v) for k, v in by_source_spans.items()},
        "parquet_uris": parquet_uris,
        "per_doc": summary,
    }
    write_json(shadow_path, shadow)
    print(f"\nspan summary: {shadow_path.relative_to(REPO_ROOT)}")
    print(f"total spans: {total_spans}")

    # Persist the actual span list separately (large file — JSON, not parquet,
    # so the verifier can diff easily). Skip if too large?
    full_path = MANIFESTS_DIR / "spans-full.json"
    write_json(full_path, by_source_spans)
    print(f"full spans: {full_path.relative_to(REPO_ROOT)}  ({full_path.stat().st_size / 1024 / 1024:.1f} MB)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
