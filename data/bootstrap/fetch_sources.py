#!/usr/bin/env python3
"""
Day 1-2 vendor fetcher — DATA-PLAN.md §8.

Reads data/sources/manifest.json. For each entry, downloads the URL with the
configured User-Agent, computes SHA-256, writes the file under data/sources/<out>,
and a sidecar <out>.sha256.

Emits a fetch report at data/manifests/fetch-report.json and updates
data/sources/README.md with the per-source provenance + hashes.

Stdlib-only (urllib + hashlib + json). Compatible with Python 3.9+.

Run from repo root:
    python3 data/bootstrap/fetch_sources.py
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCES_DIR = REPO_ROOT / "data" / "sources"
MANIFEST = SOURCES_DIR / "manifest.json"
REPORT_PATH = REPO_ROOT / "data" / "manifests" / "fetch-report.json"
README_PATH = SOURCES_DIR / "README.md"

CHUNK = 65536
TIMEOUT_SECS = 60


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def fetch_one(url: str, dest: Path, ua: str) -> dict:
    """Download url to dest. Return result dict.

    Streams to disk in chunks; computes hash after for clarity (small files).
    Honors redirects. No retries — re-run is idempotent.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECS) as resp:
            content_type = resp.headers.get("Content-Type", "")
            content_length = resp.headers.get("Content-Length")
            with dest.open("wb") as out:
                while chunk := resp.read(CHUNK):
                    out.write(chunk)
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"ok": False, "status": None, "error": f"URL error: {e.reason}"}
    except (TimeoutError, socket.timeout):
        return {"ok": False, "status": None, "error": "timeout"}
    except OSError as e:
        return {"ok": False, "status": None, "error": f"OS error: {e}"}

    size = dest.stat().st_size
    digest = sha256_file(dest)
    sidecar = dest.with_suffix(dest.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {dest.name}\n", encoding="utf-8")
    return {
        "ok": True,
        "status": 200,
        "bytes": size,
        "sha256": digest,
        "content_type": content_type,
        "content_length_header": content_length,
        "elapsed_secs": round(time.time() - started, 2),
        "sidecar": str(sidecar.relative_to(REPO_ROOT)),
    }


def render_readme(manifest: dict, results: list[dict]) -> str:
    by_id = {r["id"]: r for r in results}
    lines: list[str] = []
    lines.append("# `data/sources/` — vendored public artifacts\n")
    lines.append(
        "Day 1-2 of `docs/DATA-PLAN.md` §8. Each artifact below is downloaded "
        "from a public source and SHA-256-hashed. Hashes are recorded inline "
        "and in sidecar `<file>.sha256` files. Re-running `fetch_sources.py` "
        "is idempotent: identical sources → identical hashes.\n"
    )
    lines.append(
        "Large binaries (`.docx`, `.xlsx`, `.pdf`, `.zip`) are git-ignored and "
        "tracked by hash + URL only. Small machine-readable JSON/OSCAL files "
        "are committed in-repo for fast inspection.\n"
    )
    lines.append("## User-Agent\n")
    lines.append(f"```\n{manifest['user_agent']}\n```\n")
    lines.append("## Sources\n")
    lines.append("| ID | Format | License | SHA-256 | Bytes | Status |")
    lines.append("|---|---|---|---|---|---|")
    for src in manifest["sources"]:
        r = by_id.get(src["id"], {})
        if r.get("ok"):
            sha = f"`{r['sha256'][:16]}…`"
            size = f"{r['bytes']:,}"
            status = "ok"
        else:
            sha = "—"
            size = "—"
            status = f"FAIL: {r.get('error', 'unknown')}"
        lines.append(
            f"| `{src['id']}` | {src['format']} | {src['license']} | {sha} | {size} | {status} |"
        )
    lines.append("")
    lines.append("## Per-source detail\n")
    for src in manifest["sources"]:
        r = by_id.get(src["id"], {})
        lines.append(f"### `{src['id']}`\n")
        lines.append(f"- **Title:** {src['title']}")
        lines.append(f"- **URL:** <{src['url']}>")
        lines.append(f"- **License:** {src['license']}")
        lines.append(f"- **Out:** `data/sources/{src['out']}`")
        if "version_note" in src:
            lines.append(f"- **Version note:** {src['version_note']}")
        if "note" in src:
            lines.append(f"- **Note:** {src['note']}")
        if r.get("ok"):
            lines.append(f"- **SHA-256:** `{r['sha256']}`")
            lines.append(f"- **Bytes:** {r['bytes']:,}")
            lines.append(f"- **Content-Type:** `{r.get('content_type', '?')}`")
        else:
            lines.append(f"- **Fetch error:** {r.get('error', 'not attempted')}")
        lines.append("")
    lines.append("## Deferred sources\n")
    for d in manifest.get("deferred", []):
        lines.append(f"- **`{d['id']}`** — {d.get('title', '')}. {d['reason']}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if not MANIFEST.exists():
        print(f"manifest not found: {MANIFEST}", file=sys.stderr)
        return 2
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ua = manifest["user_agent"]

    results: list[dict] = []
    for src in manifest["sources"]:
        dest = SOURCES_DIR / src["out"]
        print(f"-> {src['id']}  {src['url']}")
        result = fetch_one(src["url"], dest, ua)
        result["id"] = src["id"]
        result["url"] = src["url"]
        result["out"] = src["out"]
        results.append(result)
        if result.get("ok"):
            print(
                f"   ok  {result['bytes']:>12,} bytes  sha256={result['sha256'][:16]}…  "
                f"{result['elapsed_secs']}s"
            )
        else:
            print(f"   FAIL  {result['error']}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nfetch report: {REPORT_PATH.relative_to(REPO_ROOT)}")

    README_PATH.write_text(render_readme(manifest, results), encoding="utf-8")
    print(f"provenance README: {README_PATH.relative_to(REPO_ROOT)}")

    failed = [r for r in results if not r.get("ok")]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
