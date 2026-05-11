#!/usr/bin/env python3
"""
DATA-PLAN.md §8 Day 3-4: BNY Investor Relations ingest.

Reads data/sources/bny-ir-targets.json — a manifest of public PDFs hosted on
bny.com (Pillar 3 quarterly disclosures, sustainability, etc.). Downloads
each, hashes, uploads to LocalStack S3 at:
    s3://bny-ddq-knowledge-raw/bny-ir/<entity>/<doc-slug>/<filename>

URLs that 404 are recorded but don't fail the run — BNY rotates older
disclosures off the live site over time. Re-runs are idempotent.

Run from repo root:
    .venv/bin/python data/bootstrap/02_fetch_bny_ir.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
from _lib import (  # noqa: E402
    MANIFESTS_DIR,
    REPO_ROOT,
    S3_KNOWLEDGE_RAW,
    SOURCES_DIR,
    TokenBucket,
    load_user_agent,
    s3_put,
    safe_get,
    sha256_bytes,
    write_json,
)

TARGETS_PATH = SOURCES_DIR / "bny-ir-targets.json"


def filename_from_url(url: str) -> str:
    return Path(urlparse(url).path).name


def main() -> int:
    if not TARGETS_PATH.exists():
        print(f"missing manifest: {TARGETS_PATH}", file=sys.stderr)
        return 2
    targets = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    base = targets["base_url"].rstrip("/")
    entity = targets["entity"]
    ua = load_user_agent()
    bucket = TokenBucket(max_per_second=8)

    flat: list[dict] = []
    for group in targets["groups"]:
        slug = group["doc_slug"]
        kind = group["kind"]
        desc = group.get("primary_desc", kind)
        for item in group["items"]:
            url = base + item["url_path"]
            flat.append({
                "kind": kind,
                "slug": slug,
                "primary_desc": desc,
                "year": item.get("year"),
                "quarter": item.get("quarter"),
                "url": url,
                "filename": filename_from_url(url),
            })

    print(f"== BNY IR ingest  entity={entity}  targets={len(flat)}  ua={ua}")

    records: list[dict] = []
    for i, t in enumerate(flat, start=1):
        s3_key = f"bny-ir/{entity}/{t['slug']}/{t['filename']}"
        rec = {**t, "s3_bucket": S3_KNOWLEDGE_RAW, "s3_key": s3_key, "ok": False}

        body, headers, err = safe_get(t["url"], ua, bucket, timeout=120)
        if err or body is None:
            rec["error"] = err
            print(f"  [{i:>2}/{len(flat)}] FAIL  {t['kind']:<8}  {t['year']}Q{t['quarter']}  {err}  {t['url']}")
            records.append(rec)
            continue

        digest = sha256_bytes(body)
        ct = (headers or {}).get("Content-Type", "application/octet-stream")
        try:
            s3_put(
                S3_KNOWLEDGE_RAW,
                s3_key,
                body,
                content_type=ct,
                metadata={
                    "source": "bny-ir",
                    "entity": entity,
                    "kind": t["kind"],
                    "year": t.get("year") or "",
                    "quarter": t.get("quarter") or "",
                    "sha256": digest,
                    "bootstrap": "true",
                },
            )
        except Exception as e:  # noqa: BLE001
            rec["error"] = f"s3 put failed: {e}"
            print(f"  [{i:>2}/{len(flat)}] FAIL  {t['kind']:<8}  {t['year']}Q{t['quarter']}  s3: {e}")
            records.append(rec)
            continue

        rec["ok"] = True
        rec["bytes"] = len(body)
        rec["sha256"] = digest
        rec["content_type"] = ct
        records.append(rec)
        print(
            f"  [{i:>2}/{len(flat)}] ok    {t['kind']:<8}  {t['year']}Q{t['quarter']}  "
            f"{len(body):>10,}b  sha256={digest[:12]}…  s3://{S3_KNOWLEDGE_RAW}/{s3_key}"
        )

    report = {
        "entity": entity,
        "fetched": len(records),
        "ok": sum(1 for r in records if r.get("ok")),
        "failed": sum(1 for r in records if not r.get("ok")),
        "deferred": targets.get("deferred", []),
        "results": records,
    }
    write_json(MANIFESTS_DIR / "bny-ir-fetch-report.json", report)

    docs = []
    for r in records:
        if not r.get("ok"):
            continue
        # Effective date: end of the reporting quarter for Pillar 3.
        effective = None
        if r.get("year") and r.get("quarter"):
            month_end = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[r["quarter"]]
            effective = f"{r['year']}-{month_end[0]:02d}-{month_end[1]:02d}"
        docs.append({
            "doc_id": f"bny-ir:{entity}:{r['slug']}:{r.get('year')}q{r.get('quarter')}",
            "source": "bny-ir",
            "entity": entity,
            "kind": r["kind"],
            "slug": r["slug"],
            "year": r.get("year"),
            "quarter": r.get("quarter"),
            "effective_date": effective,
            "primary_desc": r["primary_desc"],
            "doc_hash": f"sha256:{r['sha256']}",
            "content_type": r["content_type"],
            "bytes": r["bytes"],
            "url": r["url"],
            "s3_uri": f"s3://{r['s3_bucket']}/{r['s3_key']}",
            "tags": ["bootstrap", "bny-ir"],
            "ingested_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
    write_json(MANIFESTS_DIR / "knowledge-documents-bny-ir.json", docs)
    print(
        f"\n{report['ok']}/{report['fetched']} ok, {report['failed']} failed.  "
        f"shadow: data/manifests/knowledge-documents-bny-ir.json ({len(docs)} records)"
    )

    return 0 if report["ok"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
