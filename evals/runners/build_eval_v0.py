#!/usr/bin/env python3
"""
DATA-PLAN.md §6 — assemble the 100-item eval set v0.

Slices (per §6.1):
  30 AFME          — from library-backed canonicals; verdict=pass
  25 CAIQ          — from library-backed canonicals; verdict=pass
  15 AFME ESG      — AFME HY ESG questions; mostly verdict=halt (no BNY ESG)
  10 ADVERSARIAL   — hand-crafted; verdict=halt
  20 ADV           — hand-crafted ADV Part 1 items; verdict=halt (no ADV corpus)

Per-item schema (§6.2):
  { eval_id, framework, framework_question_ref, raw_question_text,
    expected_canonical_id, expected_evidence_spans, expected_verdict, notes }

Output:
  evals/fixtures/v0/eval_set.json
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "data" / "bootstrap"))

from _lib import MANIFESTS_DIR, s3_client  # noqa: E402

from infra.adapters.mongo_library import MongoLibrary  # noqa: E402
from infra.adapters.mongo_taxonomy import MongoTaxonomy  # noqa: E402

from pymongo import MongoClient  # noqa: E402

OUT_DIR = REPO_ROOT / "evals" / "fixtures" / "v0"
SPANS_FULL = MANIFESTS_DIR / "spans-full.json"
CAIQ_DATASET = REPO_ROOT / "data/sources/caiq/_extracted/ccm-machine-readable-bundle/CCMv4.0.12+CAIQv4.0.3-JSON-Dataset_Generated-at_2024-06-03/CAIQ/primary-dataset.json"


def short_id(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]


# ── lookup builders ──────────────────────────────────────────────
def build_afme_text_index(by_source: dict) -> dict:
    """AFME ref → question text. Ref format: AFME-3.3.11."""
    out: dict[str, str] = {}
    for s in by_source.get("afme", []):
        anchor = s.get("anchor") or {}
        if anchor.get("kind") != "section":
            continue
        sub = anchor.get("subsection")
        if not sub:
            continue
        # Use the first text we see for each ref (stable since spans are ordered).
        ref = f"AFME-{sub}"
        if ref not in out:
            out[ref] = s["text"]
    return out


def build_caiq_text_index() -> dict:
    """CAIQ qid → question body."""
    body = json.loads(CAIQ_DATASET.read_text(encoding="utf-8"))
    return {q["id"]: " ".join((q.get("body") or "").split()) for q in body.get("questions", [])}


def build_afme_esg_pool(by_source: dict) -> list[dict]:
    """AFME HY ESG paragraphs that became canon.esg.afme_hy.* canonicals."""
    out: list[dict] = []
    for s in by_source.get("afme", []):
        prov = s.get("provenance") or {}
        extra = prov.get("extra") or {}
        if extra.get("variant") != "hy_esg":
            continue
        text = (s.get("text") or "").strip()
        if len(text) < 220:
            continue
        anchor = s.get("anchor") or {}
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
        out.append({
            "ref": f"AFME-HY-ESG-p{anchor.get('page')}-{h}",
            "text": text,
            "page": anchor.get("page"),
        })
    return out


# ── slice builders ───────────────────────────────────────────────
def build_pass_slice(
    framework: str, target_count: int, lib_entries, taxonomy_lookup, ref_text_index
) -> list[dict]:
    """Pass slice: library-backed canonicals with refs in this framework.

    Within-slice dedup (same canonical can't appear twice in this slice with
    two different refs); across-slice OK — same canonical may be probed from
    AFME *and* CAIQ angles, that's the point of cross-framework deflection.
    Each library entry contributes at most one item per slice.
    """
    out: list[dict] = []
    used_in_slice: set[str] = set()
    for entry in lib_entries:
        if len(out) >= target_count:
            break
        if entry.canonical_id in used_in_slice:
            continue
        canonical = taxonomy_lookup.get(entry.canonical_id)
        if not canonical:
            continue
        # Pick a ref in this framework whose question text is non-trivially long.
        chosen_ref = None
        chosen_version = None
        chosen_text = None
        for m in canonical.framework_mappings:
            if m.framework != framework:
                continue
            text = ref_text_index.get(m.question_ref)
            if text and len(text) >= 30:
                chosen_ref = m.question_ref
                chosen_version = m.version
                chosen_text = text
                break
        if not chosen_ref:
            continue
        eid = f"ev_{short_id(chosen_ref + entry.entry_id)}"
        out.append({
            "eval_id": eid,
            "framework": framework,
            "framework_question_ref": chosen_ref,
            "framework_version": chosen_version,
            "raw_question_text": chosen_text,
            "expected_canonical_id": entry.canonical_id,
            "expected_evidence_spans": [
                {
                    "doc_hash": r.doc_hash,
                    "span_hash": r.span_hash,
                    "anchor": r.anchor,
                    "doc_id": r.doc_id,
                    "span_id": r.span_id,
                }
                for r in entry.evidence_refs
            ],
            "expected_verdict": "pass",
            "notes": f"library-backed (entry {entry.entry_id})",
        })
        used_in_slice.add(entry.canonical_id)
    return out


def build_esg_slice(target_count: int, esg_pool: list[dict]) -> list[dict]:
    """AFME HY ESG questions — verdict=halt (no BNY ESG in corpus)."""
    out: list[dict] = []
    for item in esg_pool[:target_count]:
        eid = f"ev_{short_id(item['ref'])}"
        # Use first ~250 chars of the paragraph as the "question" — phrasing it
        # like a DDQ ask is a stretch but the eval scores retrieval over the
        # full text, so this still measures recall meaningfully.
        text = item["text"]
        question = "Describe BNY's approach to: " + text[:240]
        out.append({
            "eval_id": eid,
            "framework": "AFME_ESG",
            "framework_question_ref": item["ref"],
            "framework_version": "2026-01",
            "raw_question_text": question,
            "expected_canonical_id": None,
            "expected_evidence_spans": [],
            "expected_verdict": "halt",
            "notes": "BNY sustainability disclosures not yet ingested (Day 3-4 gap); citation guardrail should halt.",
        })
    return out


def build_adversarial_slice() -> list[dict]:
    """Hand-crafted; should produce halt or weak retrieval."""
    items = [
        ("Describe BNY's quantum cryptography migration roadmap and key timeline milestones.",
         "speculative; not in 10-K, Pillar 3, or DEF 14A"),
        ("List the specific MFA hardware tokens issued to BNY's privileged operators in EMEA.",
         "operational detail not in public filings"),
        ("Provide the exact CrowdStrike sensor version installed on BNY trading desks as of 2026.",
         "vendor-specific operational detail"),
        ("What is BNY's policy on remote-work background checks for contractors based in Belarus?",
         "narrow geographic + role detail not disclosed"),
        ("Disclose the cipher suite used by BNY's external SFTP gateway with state-street counterparties.",
         "client-specific commercial detail"),
        ("Identify each ATM location operated by BNY across North America with daily transaction volumes.",
         "BNY does not operate retail ATMs at material scale; not in disclosures"),
        ("How many penetration tests did BNY conduct in Q3 2025 and what were the CVSS scores?",
         "internal red-team detail not disclosed"),
        ("List specific salary ranges paid to BNY infosec staff by tenure band.",
         "HR detail not in proxy summary comp"),
        ("Provide BNY's HSM model numbers and the firmware versions deployed in each datacenter.",
         "hardware inventory detail not disclosed"),
        ("Summarize the verbatim contents of BNY's customer master agreement with Vanguard.",
         "client-specific contract; would also fail confidentiality scrub"),
    ]
    out: list[dict] = []
    for i, (q, why) in enumerate(items):
        eid = f"ev_{short_id('adv:' + q)}"
        out.append({
            "eval_id": eid,
            "framework": "ADVERSARIAL",
            "framework_question_ref": f"ADVERSARIAL-{i+1:02d}",
            "framework_version": "v0",
            "raw_question_text": q,
            "expected_canonical_id": None,
            "expected_evidence_spans": [],
            "expected_verdict": "halt",
            "notes": why,
        })
    return out


def build_adv_slice() -> list[dict]:
    """ADV Part 1 schedule items — hand-rolled. Mostly halt: ADV not yet ingested."""
    items = [
        ("Provide your firm's CRD number and SEC file number.", "ADV Part 1 Item 1"),
        ("Identify each principal owner with 25% or more direct or indirect equity in the firm.",
         "ADV Part 1 Schedule A — direct owners ≥25%"),
        ("List all related advisers under common control with the firm.",
         "ADV Part 1 Item 7.A — control affiliations"),
        ("Disclose any disciplinary or regulatory action against the firm or its principals in the past 10 years.",
         "ADV Part 1 Item 11 — DRPs"),
        ("State the firm's regulatory assets under management (RAUM) as of the most recent fiscal year end.",
         "ADV Part 1 Item 5.F — RAUM"),
        ("Identify the firm's primary custodian and any related-party custody arrangements.",
         "ADV Part 1 Item 9 — custody"),
        ("Disclose the firm's principal office and place of business.",
         "ADV Part 1 Item 1.F"),
        ("List the types of clients the firm advises (institutional, HNW, mutual fund, etc.).",
         "ADV Part 1 Item 5.D — client types"),
        ("State the number of employees performing investment-advisory functions.",
         "ADV Part 1 Item 5.B"),
        ("Disclose the firm's wrap-fee program participation, if any.",
         "ADV Part 1 Item 5.I"),
        ("Provide the names and CRD numbers of all officers and directors.",
         "ADV Part 1 Schedule A & B"),
        ("List any indirect owners with 25% or more beneficial interest.",
         "ADV Part 1 Schedule B"),
        ("State whether the firm acts as a sponsor of a wrap-fee program.",
         "ADV Part 1 Item 5.I.1"),
        ("Disclose any pending civil claims for damages exceeding USD 2,500.",
         "ADV Part 1 Item 11.H"),
        ("Identify each non-US regulator that has authority over the firm.",
         "ADV Part 1 Item 7.A.2"),
        ("State the percentage of clients that are pension/profit-sharing plans.",
         "ADV Part 1 Item 5.D.3"),
        ("Disclose if the firm is registered with state securities authorities.",
         "ADV Part 1 Item 2"),
        ("Identify all branches conducting advisory business outside the principal office.",
         "ADV Part 1 Section 1.F"),
        ("State the gross compensation for performance-based fees in the prior fiscal year.",
         "ADV Part 1 Item 5.E"),
        ("Disclose any non-standard custody practices including SLOAs and standing instructions.",
         "ADV Part 1 Item 9.A"),
    ]
    out: list[dict] = []
    for i, (q, ref) in enumerate(items):
        eid = f"ev_{short_id('adv-form:' + q)}"
        out.append({
            "eval_id": eid,
            "framework": "ADV",
            "framework_question_ref": f"ADV-PART1-{i+1:02d}",
            "framework_version": "2026",
            "raw_question_text": q,
            "expected_canonical_id": None,
            "expected_evidence_spans": [],
            "expected_verdict": "halt",
            "notes": f"{ref}; ADV bulk + per-firm corpus deferred to Day 10.5 — no evidence available, citation guardrail must halt.",
        })
    return out


# ── main ─────────────────────────────────────────────────────────
def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("== Loading state ==")
    mongo = MongoClient("mongodb://ddq:ddq-dev@localhost:27018", serverSelectionTimeoutMS=5000)
    s3 = s3_client()
    tax = MongoTaxonomy(mongo, s3)
    lib = MongoLibrary(mongo, s3)
    canonicals = list(tax.list_all())
    taxonomy_lookup = {c.canonical_id: c for c in canonicals}
    lib_entries = list(lib.list_all())
    print(f"  canonicals: {len(canonicals)}  library entries: {len(lib_entries)}")

    by_source = json.loads(SPANS_FULL.read_text(encoding="utf-8"))
    afme_idx = build_afme_text_index(by_source)
    caiq_idx = build_caiq_text_index()
    esg_pool = build_afme_esg_pool(by_source)
    print(f"  AFME refs indexed: {len(afme_idx)}  CAIQ qids: {len(caiq_idx)}  HY ESG paragraphs: {len(esg_pool)}")

    print("\n== Building slices ==")
    afme = build_pass_slice("AFME", 30, lib_entries, taxonomy_lookup, afme_idx)
    print(f"  AFME slice  : {len(afme)} (target 30)")
    caiq = build_pass_slice("CAIQ", 25, lib_entries, taxonomy_lookup, caiq_idx)
    print(f"  CAIQ slice  : {len(caiq)} (target 25)")
    esg = build_esg_slice(15, esg_pool)
    print(f"  ESG slice   : {len(esg)} (target 15)")
    adv_ = build_adversarial_slice()
    print(f"  ADVERSARIAL : {len(adv_)} (target 10)")
    adv_form = build_adv_slice()
    print(f"  ADV slice   : {len(adv_form)} (target 20)")

    items = afme + caiq + esg + adv_ + adv_form
    print(f"\n  total: {len(items)}")

    # Validate uniqueness.
    eval_ids = [it["eval_id"] for it in items]
    assert len(eval_ids) == len(set(eval_ids)), "duplicate eval_id"

    out = {
        "version": "v0",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "corpus_pin": {
            "knowledge_documents_path": str((MANIFESTS_DIR / "knowledge-documents.json").relative_to(REPO_ROOT)),
            "taxonomy_version": "tx_v0.1",
            "library_version": "lib_v0.1",
        },
        "counts": {
            "AFME": len(afme), "CAIQ": len(caiq), "AFME_ESG": len(esg),
            "ADVERSARIAL": len(adv_), "ADV": len(adv_form),
            "total": len(items),
        },
        "items": items,
    }
    (OUT_DIR / "eval_set.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote: {(OUT_DIR / 'eval_set.json').relative_to(REPO_ROOT)}  ({len(items)} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
