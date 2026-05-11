#!/usr/bin/env python3
"""
DATA-PLAN.md §3.6 AC #3 — anchor resolution acceptance.

Two checks:
  1. Hash integrity: for N random spans across all sources, verify
     span_hash == sha256(text.encode('utf-8')).
  2. Determinism: re-parse one doc per source and verify the resulting
     tuple stream is bit-identical to the persisted spans.json.

Re-parses pull bytes from LocalStack S3 (BNY corpus) or local disk
(framework sources), exactly as 03_parse_corpus.py does.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import MANIFESTS_DIR, REPO_ROOT, s3_client  # noqa: E402

SPANS_FULL = MANIFESTS_DIR / "spans-full.json"


def text_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_hash_integrity(by_source: dict[str, list[dict]], sample_size: int) -> dict:
    """Sample N random spans across every source and verify span_hash."""
    rng = random.Random(20260509)  # deterministic
    flat = []
    for src, spans in by_source.items():
        for s in spans:
            flat.append((src, s))
    n = min(sample_size, len(flat))
    sample = rng.sample(flat, n)
    failures = []
    for src, s in sample:
        recomputed = text_hash(s["text"])
        if recomputed != s["span_hash"]:
            failures.append({"source": src, "span_id": s["span_id"], "expected": s["span_hash"], "got": recomputed})
    return {"sampled": n, "failures": failures, "pass": not failures}


def reparse_one_per_source(by_source: dict[str, list[dict]]) -> dict:
    """Pick one doc per source, re-parse, compare tuple streams."""
    sys.path.insert(0, str(Path(__file__).parent))
    from parsers import caiq_json, docx_parse, edgar_html, pdf_pymupdf  # noqa: PLC0415
    from _lib import S3_KNOWLEDGE_RAW  # noqa: PLC0415, F401

    s3 = s3_client()
    edgar_ir = json.loads((MANIFESTS_DIR / "knowledge-documents.json").read_text(encoding="utf-8"))
    ir_by_id = {d["doc_id"]: d for d in edgar_ir}

    results: dict[str, dict] = {}

    def reparse(doc_meta: dict, body: bytes) -> list[dict]:
        src = doc_meta.get("source", "")
        if src == "edgar":
            it = edgar_html.parse_edgar_html(
                body=body, doc_id=doc_meta["doc_id"], doc_hash=doc_meta["doc_hash"],
                form=doc_meta["form"], filing_date=doc_meta["filing_date"], accession=doc_meta["accession"],
            )
        elif src == "bny-ir":
            it = pdf_pymupdf.parse_pdf(body=body, doc_id=doc_meta["doc_id"], doc_hash=doc_meta["doc_hash"],
                source="bny-ir",
                extra={"kind": doc_meta.get("kind"), "year": doc_meta.get("year"), "quarter": doc_meta.get("quarter")})
        elif src == "caiq":
            it = caiq_json.parse_caiq_questions(body=body, doc_id=doc_meta["doc_id"], doc_hash=doc_meta["doc_hash"])
        elif src == "ccm":
            it = caiq_json.parse_ccm_controls(body=body, doc_id=doc_meta["doc_id"], doc_hash=doc_meta["doc_hash"])
        elif src in ("nist_csf", "nist_800_53"):
            it = caiq_json.parse_oscal_catalog(body=body, doc_id=doc_meta["doc_id"], doc_hash=doc_meta["doc_hash"],
                source=src, framework=doc_meta["framework"])
        elif src == "afme":
            if doc_meta["kind"] == "docx":
                it = docx_parse.parse_docx(body=body, doc_id=doc_meta["doc_id"], doc_hash=doc_meta["doc_hash"],
                    source="afme", extra=doc_meta.get("extra"))
            else:
                it = pdf_pymupdf.parse_pdf(body=body, doc_id=doc_meta["doc_id"], doc_hash=doc_meta["doc_hash"],
                    source="afme", extra=doc_meta.get("extra"))
        else:
            return []
        return [s.to_dict() for s in it]

    # Framework documents — keep in sync with 03_parse_corpus.framework_documents()
    framework_meta = {
        "caiq": {"doc_id": "caiq:v4.0.3:primary-dataset", "kind": "caiq_questions", "source": "caiq",
                 "rel_path": "data/sources/caiq/_extracted/ccm-machine-readable-bundle/CCMv4.0.12+CAIQv4.0.3-JSON-Dataset_Generated-at_2024-06-03/CAIQ/primary-dataset.json"},
        "ccm": {"doc_id": "ccm:v4.0.12:primary-dataset", "kind": "ccm_controls", "source": "ccm",
                "rel_path": "data/sources/caiq/_extracted/ccm-machine-readable-bundle/CCMv4.0.12+CAIQv4.0.3-JSON-Dataset_Generated-at_2024-06-03/CCM/primary-dataset.json"},
        "nist_csf": {"doc_id": "nist:csf:v2.0:catalog", "kind": "oscal_catalog", "source": "nist_csf",
                     "framework": "NIST_CSF_v2.0", "rel_path": "data/sources/nist/NIST_CSF_v2.0_catalog.json"},
        "nist_800_53": {"doc_id": "nist:sp800-53:rev5:catalog", "kind": "oscal_catalog", "source": "nist_800_53",
                        "framework": "NIST_SP800_53_rev5", "rel_path": "data/sources/nist/NIST_SP-800-53_rev5_catalog.json"},
        "afme": {"doc_id": "afme:ddq-custodian:2026", "kind": "docx", "source": "afme",
                 "rel_path": "data/sources/afme/afme-ddq-custodian-2026.docx",
                 "extra": {"variant": "custodian", "year": 2026}},
    }

    for src, spans in by_source.items():
        if not spans:
            continue
        target_doc_id = spans[0]["doc_id"]
        # Find the doc metadata + body.
        if src in framework_meta and framework_meta[src]["doc_id"] == target_doc_id:
            meta = framework_meta[src]
            body = (REPO_ROOT / meta["rel_path"]).read_bytes()
            doc_hash = "sha256:" + hashlib.sha256(body).hexdigest()
            meta_with_hash = {**meta, "doc_hash": doc_hash}
        elif target_doc_id in ir_by_id:
            meta = ir_by_id[target_doc_id]
            bucket, key = meta["s3_uri"].removeprefix("s3://").split("/", 1)
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            meta_with_hash = meta
        else:
            results[src] = {"pass": None, "note": "could not locate source doc for re-parse"}
            continue

        re_spans = reparse(meta_with_hash, body)
        original = [s for s in spans if s["doc_id"] == target_doc_id]
        # Compare ignoring `provenance.ingested_at` since wall clock changes.
        def strip_ts(d):
            d = dict(d)
            prov = dict(d.get("provenance") or {})
            prov.pop("ingested_at", None)
            d["provenance"] = prov
            return d

        a = [strip_ts(s) for s in original]
        b = [strip_ts(s) for s in re_spans]
        if a == b:
            results[src] = {"pass": True, "doc_id": target_doc_id, "spans": len(a)}
        else:
            # Find first difference for diagnostics.
            diff_idx = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), -1)
            results[src] = {
                "pass": False,
                "doc_id": target_doc_id,
                "original_count": len(a),
                "reparse_count": len(b),
                "first_diff_index": diff_idx,
            }
    return results


def main() -> int:
    if not SPANS_FULL.exists():
        print(f"missing {SPANS_FULL}; run 03_parse_corpus.py first", file=sys.stderr)
        return 2
    by_source = json.loads(SPANS_FULL.read_text(encoding="utf-8"))
    total = sum(len(v) for v in by_source.values())
    print(f"== Acceptance: {total} spans across {len(by_source)} sources")

    print("\n== Hash integrity (DATA-PLAN §3.6 AC #3) ==")
    integ = check_hash_integrity(by_source, sample_size=500)
    print(f"  sampled: {integ['sampled']}  failures: {len(integ['failures'])}  -> {'PASS' if integ['pass'] else 'FAIL'}")
    for f in integ["failures"][:5]:
        print(f"    {f}")

    print("\n== Determinism (re-parse, byte-identical tuples) ==")
    det = reparse_one_per_source(by_source)
    det_pass = all(r.get("pass") for r in det.values() if r.get("pass") is not None)
    for src, r in det.items():
        flag = "PASS" if r.get("pass") else ("n/a " if r.get("pass") is None else "FAIL")
        if r.get("pass"):
            print(f"  {flag}  {src:<14}  {r.get('doc_id', '?')}  spans={r['spans']}")
        else:
            print(f"  {flag}  {src:<14}  {r}")

    report = {"hash_integrity": integ, "determinism": det, "by_source_counts": {k: len(v) for k, v in by_source.items()}, "total_spans": total}
    out = MANIFESTS_DIR / "parse-acceptance.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nreport: {out.relative_to(REPO_ROOT)}")
    overall_pass = integ["pass"] and det_pass
    print(f"\noverall: {'PASS' if overall_pass else 'FAIL'}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
