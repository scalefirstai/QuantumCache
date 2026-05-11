#!/usr/bin/env python3
"""
DATA-PLAN.md §8 Day 3-4: SEC EDGAR ingest for BNY Mellon Corp (CIK 1390777).

Walks the submissions index (recent + paginated older files), filters to
target form types within the last 5 years, downloads each filing's primary
document, hashes it, and uploads to LocalStack S3 at:
    s3://bny-ddq-knowledge-raw/edgar/<entity-slug>/<accession>/<filename>

Honors SEC fair-access policy: User-Agent header per DATA-PLAN §3.3, rate
limited to 8 req/sec (DATA-PLAN §9 risk #3 ceiling is 10/sec; we leave 2/sec
headroom). Re-runs are idempotent — same source bytes → same hash → same key.

Run from repo root:
    .venv/bin/python data/bootstrap/01_fetch_edgar.py
or:
    .venv/bin/python data/bootstrap/01_fetch_edgar.py --years 3 --forms 10-K,10-Q
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

# Allow running as a script from anywhere.
sys.path.insert(0, str(Path(__file__).parent))
from _lib import (  # noqa: E402
    MANIFESTS_DIR,
    REPO_ROOT,
    S3_KNOWLEDGE_RAW,
    TokenBucket,
    load_user_agent,
    s3_put,
    safe_get,
    sha256_bytes,
    write_json,
)

CIK = "0001390777"
ENTITY_SLUG = "bny-mellon-corp"
ENTITY_NAME = "Bank of New York Mellon Corp"
SUBMISSIONS_URL = f"https://data.sec.gov/submissions/CIK{CIK}.json"
ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"
DEFAULT_FORMS = ("10-K", "10-Q", "8-K", "DEF 14A")
DEFAULT_YEARS = 5


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch BNY EDGAR filings into LocalStack S3.")
    p.add_argument(
        "--forms",
        default=",".join(DEFAULT_FORMS),
        help=f"Comma-separated form types. Default: {','.join(DEFAULT_FORMS)}.",
    )
    p.add_argument(
        "--years",
        type=int,
        default=DEFAULT_YEARS,
        help=f"Years of history to fetch. Default: {DEFAULT_YEARS}.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max documents to fetch (0 = unlimited). Useful for smoke-tests.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="List filings that would be fetched; don't download or upload.",
    )
    return p.parse_args(argv)


def iter_submission_indexes(ua: str, bucket: TokenBucket):
    """Yield each submissions index dict (recent block + each paginated file)."""
    body, _, err = safe_get(SUBMISSIONS_URL, ua, bucket)
    if err or body is None:
        raise RuntimeError(f"failed to fetch submissions index: {err}")
    root = json.loads(body)
    yield root["filings"]["recent"]
    for f in root["filings"].get("files", []):
        url = f"https://data.sec.gov/submissions/{f['name']}"
        b, _, err = safe_get(url, ua, bucket)
        if err or b is None:
            print(f"  warn: paginated index fetch failed: {f['name']} ({err})")
            continue
        # Paginated files contain just the same array fields, no wrapper.
        yield json.loads(b)


def collect_filings(
    ua: str,
    bucket: TokenBucket,
    forms: set[str],
    cutoff: dt.date,
) -> list[dict]:
    """Build the filtered filing list across recent + paginated indexes.

    Each entry: { accession, accession_clean, form, filing_date, primary_doc, primary_desc, archive_url }
    """
    out: list[dict] = []
    for block in iter_submission_indexes(ua, bucket):
        accs = block.get("accessionNumber", [])
        forms_arr = block.get("form", [])
        dates = block.get("filingDate", [])
        prims = block.get("primaryDocument", [])
        descs = block.get("primaryDocDescription", [""] * len(accs))
        for i, acc in enumerate(accs):
            form = forms_arr[i]
            if form not in forms:
                continue
            try:
                fdate = dt.date.fromisoformat(dates[i])
            except ValueError:
                continue
            if fdate < cutoff:
                continue
            primary = prims[i]
            if not primary:
                continue
            acc_clean = acc.replace("-", "")
            out.append({
                "accession": acc,
                "accession_clean": acc_clean,
                "form": form,
                "filing_date": dates[i],
                "primary_doc": primary,
                "primary_desc": descs[i] if i < len(descs) else "",
                "archive_url": f"{ARCHIVE_BASE}/{int(CIK)}/{acc_clean}/{primary}",
            })
    out.sort(key=lambda r: r["filing_date"], reverse=True)
    return out


def fetch_and_upload(
    filings: list[dict],
    ua: str,
    bucket: TokenBucket,
    limit: int,
    dry_run: bool,
) -> list[dict]:
    """Download each filing's primary document, hash, upload. Return per-doc records."""
    records: list[dict] = []
    target = filings[:limit] if limit > 0 else filings
    for i, f in enumerate(target, start=1):
        s3_key = f"edgar/{ENTITY_SLUG}/{f['accession']}/{f['primary_doc']}"
        rec = {
            **f,
            "s3_bucket": S3_KNOWLEDGE_RAW,
            "s3_key": s3_key,
            "ok": False,
        }
        if dry_run:
            print(f"  [{i:>3}/{len(target)}] DRY  {f['form']:<8}  {f['filing_date']}  -> {s3_key}")
            records.append(rec)
            continue

        body, headers, err = safe_get(f["archive_url"], ua, bucket, timeout=120)
        if err or body is None:
            rec["error"] = err or "no body"
            print(f"  [{i:>3}/{len(target)}] FAIL {f['form']:<8}  {f['filing_date']}  {err}")
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
                    "source": "edgar",
                    "entity": ENTITY_SLUG,
                    "form": f["form"],
                    "filing_date": f["filing_date"],
                    "accession": f["accession"],
                    "sha256": digest,
                    "bootstrap": "true",
                },
            )
        except Exception as e:  # noqa: BLE001
            rec["error"] = f"s3 put failed: {e}"
            print(f"  [{i:>3}/{len(target)}] FAIL {f['form']:<8}  {f['filing_date']}  s3: {e}")
            records.append(rec)
            continue

        rec["ok"] = True
        rec["bytes"] = len(body)
        rec["sha256"] = digest
        rec["content_type"] = ct
        records.append(rec)
        print(
            f"  [{i:>3}/{len(target)}] ok   {f['form']:<8}  {f['filing_date']}  "
            f"{len(body):>10,}b  sha256={digest[:12]}…  s3://{S3_KNOWLEDGE_RAW}/{s3_key}"
        )
    return records


def write_documents_index(records: list[dict]) -> None:
    """Emit a knowledge.documents-shaped index per ddq.md §5.

    Mongo collection `knowledge.documents` holds metadata only; bodies stay
    in S3. This file is the offline shadow and the input to L01/L03 ingest.
    """
    docs = []
    for r in records:
        if not r.get("ok"):
            continue
        docs.append({
            "doc_id": f"edgar:{ENTITY_SLUG}:{r['accession']}",
            "source": "edgar",
            "entity": ENTITY_SLUG,
            "entity_name": ENTITY_NAME,
            "form": r["form"],
            "filing_date": r["filing_date"],
            "accession": r["accession"],
            "primary_doc": r["primary_doc"],
            "primary_desc": r.get("primary_desc", ""),
            "archive_url": r["archive_url"],
            "doc_hash": f"sha256:{r['sha256']}",
            "content_type": r["content_type"],
            "bytes": r["bytes"],
            "s3_uri": f"s3://{r['s3_bucket']}/{r['s3_key']}",
            "tags": ["bootstrap", "edgar"],
            "ingested_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
    write_json(MANIFESTS_DIR / "knowledge-documents-edgar.json", docs)
    print(f"wrote knowledge.documents shadow: {len(docs)} records -> data/manifests/knowledge-documents-edgar.json")


def main() -> int:
    args = parse_args()
    ua = load_user_agent()
    forms = {f.strip() for f in args.forms.split(",") if f.strip()}
    cutoff = dt.date.today() - dt.timedelta(days=365 * args.years)
    bucket = TokenBucket(max_per_second=8)

    print(f"== EDGAR ingest  CIK={CIK}  entity='{ENTITY_NAME}'")
    print(f"   forms={sorted(forms)}  cutoff={cutoff.isoformat()}  ua={ua}")

    print("\n== Collecting filing index ==")
    filings = collect_filings(ua, bucket, forms, cutoff)
    by_form: dict[str, int] = {}
    for f in filings:
        by_form[f["form"]] = by_form.get(f["form"], 0) + 1
    print(f"   {len(filings)} filings match.  by form: {by_form}")

    if args.limit:
        print(f"   limiting to {args.limit} (smoke-test)")

    print("\n== Fetching primary documents ==")
    records = fetch_and_upload(filings, ua, bucket, args.limit, args.dry_run)

    report_path = MANIFESTS_DIR / "edgar-fetch-report.json"
    write_json(report_path, {
        "cik": CIK,
        "entity": ENTITY_NAME,
        "cutoff": cutoff.isoformat(),
        "forms": sorted(forms),
        "by_form": by_form,
        "results": records,
    })
    print(f"\nfetch report: {report_path.relative_to(REPO_ROOT)}")

    if not args.dry_run:
        write_documents_index(records)

    failed = [r for r in records if not r.get("ok") and not args.dry_run]
    if args.dry_run:
        return 0
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
