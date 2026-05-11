#!/usr/bin/env python3
"""
Day 1-2 verifier — DATA-PLAN.md §8 acceptance:
  - CAIQ machine-readable JSON loads cleanly
  - CCM mapping bundle covers NIST 800-53, ISO 27001, PCI, SOC 2.

Operates against whatever fetch_sources.py produced. The CSA bundle is a zip
containing a directory tree of JSON/YAML/XLSX. We unzip in-place to
data/sources/caiq/_extracted/ and inspect contents.

Stdlib-only.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCES_DIR = REPO_ROOT / "data" / "sources"
CAIQ_DIR = SOURCES_DIR / "caiq"
NIST_DIR = SOURCES_DIR / "nist"
EXTRACT_DIR = CAIQ_DIR / "_extracted"


REQUIRED_MAPPING_TARGETS = [
    # DATA-PLAN §8 Day 1-2: "verify CCM mapping bundle covers
    # NIST 800-53, ISO 27001, PCI, SOC 2." CSA names mappings by source
    # standard, so SOC 2 = AICPA Trust Services Criteria (TSC).
    ("nist_800_53", ["nist_800_53", "800-53", "sp800-53"]),
    ("iso_27001", ["iso27001", "iso_27001"]),
    ("pci_dss", ["pci_dss", "pci-dss"]),
    ("soc2_aicpa_tsc", ["aicpa_tsc", "aicpa-tsc", "soc2", "soc_2"]),
]


def extract_all_zips() -> list[Path]:
    extracted: list[Path] = []
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    for zpath in sorted(CAIQ_DIR.glob("*.zip")):
        target = EXTRACT_DIR / zpath.stem
        if target.exists():
            print(f"  already extracted: {target.relative_to(REPO_ROOT)}")
            extracted.append(target)
            continue
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(target)
        print(f"  extracted: {zpath.name} -> {target.relative_to(REPO_ROOT)}")
        extracted.append(target)
    return extracted


def find_caiq_json(roots: list[Path]) -> list[Path]:
    """Find any JSON file under a CAIQ/ directory or with CAIQ-ish name.

    CSA's machine-readable bundle places the questionnaire at
    `<release>/CAIQ/primary-dataset.json` — the filename is generic, so we
    also accept any *.json under a path component named CAIQ.
    """
    candidates: list[Path] = []
    for root in roots:
        for p in root.rglob("*.json"):
            if "__MACOSX" in p.parts:
                continue
            name = p.name.lower()
            in_caiq_dir = any(part.upper() == "CAIQ" for part in p.parts)
            if in_caiq_dir or "caiq" in name or "questionnaire" in name:
                candidates.append(p)
    return candidates


def verify_caiq_json(path: Path) -> dict:
    """Return summary dict — load cleanly, count question-like records."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return {"path": str(path.relative_to(REPO_ROOT)), "ok": False, "error": f"JSON parse: {e}"}
    except OSError as e:
        return {"path": str(path.relative_to(REPO_ROOT)), "ok": False, "error": f"IO: {e}"}

    # CAIQ JSON shape varies by year; we accept any of:
    #   {"questions": [...]} / {"controls": [...]} / list[ {...} ]
    # Just count plausible question records to sanity-check.
    count = 0
    if isinstance(data, dict):
        for key in ("questions", "controls", "items", "data"):
            if isinstance(data.get(key), list):
                count = len(data[key])
                break
        if count == 0:
            count = sum(1 for v in data.values() if isinstance(v, list))
    elif isinstance(data, list):
        count = len(data)

    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "ok": True,
        "top_level": type(data).__name__,
        "approx_record_count": count,
        "size_bytes": path.stat().st_size,
    }


def find_mapping_coverage(roots: list[Path]) -> dict:
    """Walk extracted bundles and check filenames/paths for each required target.

    DATA-PLAN expects the CCM mapping bundle to ship pre-built mappings to
    NIST 800-53, ISO 27001, PCI, SOC 2 (and more). Filenames typically include
    the framework name. We use a substring match on path components.
    """
    all_files: list[Path] = []
    for root in roots:
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if "__MACOSX" in p.parts:
                continue
            all_files.append(p)

    coverage = {}
    for label, needles in REQUIRED_MAPPING_TARGETS:
        matches = [
            p
            for p in all_files
            if any(n in str(p).lower() for n in needles)
        ]
        coverage[label] = {
            "found": bool(matches),
            "matches": [str(p.relative_to(REPO_ROOT)) for p in matches[:8]],
            "match_count": len(matches),
        }
    return coverage


def verify_nist_oscal() -> list[dict]:
    """Quick parse-check of the NIST OSCAL JSON catalogs."""
    out = []
    for p in sorted(NIST_DIR.glob("*.json")):
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            # OSCAL catalogs have a top-level "catalog" key.
            shape = list(data.keys())[:3] if isinstance(data, dict) else type(data).__name__
            out.append({"path": str(p.relative_to(REPO_ROOT)), "ok": True, "top_keys": shape, "size_bytes": p.stat().st_size})
        except Exception as e:  # noqa: BLE001
            out.append({"path": str(p.relative_to(REPO_ROOT)), "ok": False, "error": str(e)})
    return out


def main() -> int:
    if not CAIQ_DIR.exists():
        print(f"caiq dir not found: {CAIQ_DIR}", file=sys.stderr)
        return 2

    print("== Extracting CSA zip bundles ==")
    extracted = extract_all_zips()
    if not extracted:
        print("  no zips found — did fetch_sources.py succeed for csa.* entries?")

    print("\n== CAIQ JSON load check ==")
    caiq_jsons = find_caiq_json(extracted)
    caiq_results = [verify_caiq_json(p) for p in caiq_jsons]
    if not caiq_results:
        print("  no CAIQ JSON found in extracted bundles")
    for r in caiq_results:
        if r.get("ok"):
            print(
                f"  ok  {r['path']}  top={r['top_level']}  "
                f"records~={r['approx_record_count']}  bytes={r['size_bytes']:,}"
            )
        else:
            print(f"  FAIL  {r['path']}  {r['error']}")

    print("\n== CCM mapping coverage ==")
    coverage = find_mapping_coverage(extracted)
    for label, info in coverage.items():
        flag = "ok" if info["found"] else "MISSING"
        print(f"  {flag:>7}  {label:<10}  matches={info['match_count']}")
        for m in info["matches"][:3]:
            print(f"            - {m}")

    print("\n== NIST OSCAL catalog parse check ==")
    nist_results = verify_nist_oscal()
    for r in nist_results:
        if r.get("ok"):
            print(f"  ok  {r['path']}  keys={r['top_keys']}  bytes={r['size_bytes']:,}")
        else:
            print(f"  FAIL  {r['path']}  {r['error']}")

    report = {
        "caiq_json_load": caiq_results,
        "ccm_mapping_coverage": coverage,
        "nist_oscal_parse": nist_results,
    }
    out_path = REPO_ROOT / "data" / "manifests" / "verify-report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nverify report: {out_path.relative_to(REPO_ROOT)}")

    # Acceptance: CAIQ loads & all four mapping targets covered.
    caiq_ok = bool(caiq_results) and all(r.get("ok") for r in caiq_results)
    mapping_ok = all(info["found"] for info in coverage.values())
    nist_ok = bool(nist_results) and all(r.get("ok") for r in nist_results)
    if caiq_ok and mapping_ok and nist_ok:
        print("\nACCEPTANCE: PASS  (CAIQ loads · mapping coverage complete · NIST OSCAL parses)")
        return 0
    print("\nACCEPTANCE: FAIL")
    if not caiq_ok:
        print("  - CAIQ JSON did not load cleanly")
    if not mapping_ok:
        missing = [k for k, v in coverage.items() if not v["found"]]
        print(f"  - missing mapping coverage: {missing}")
    if not nist_ok:
        print("  - NIST OSCAL did not parse")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
