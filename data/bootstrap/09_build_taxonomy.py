#!/usr/bin/env python3
"""
DATA-PLAN.md §8 Day 8 — taxonomy v0.1 cut.

Pipeline:
  1. Load CAIQ questions + CCM controls + 5 CCM crosswalk JSONs
     (NIST 800-53 rev5, ISO 27001:2022, PCI DSS v4.0, AICPA TSC 2017,
     NIST CSF v2.0).
  2. Mint a CanonicalQuestion for every CAIQ question, with
     framework_mappings = [CAIQ self] + crosswalk lookups for this question's
     parent CCM control.
  3. For every AFME question span (subsection-tagged), embed and look up
     nearest CAIQ canonical in Qdrant. Above SIM_THRESHOLD → append AFME
     mapping to that canonical; below → mint a new canon.subc.* /
     canon.or.* / canon.esg.* entry based on AFME section.
  4. Write everything through `MongoTaxonomy.upsert` (the port adapter).
  5. Generate ed25519 signing key, `cut_version("tx_v0.1")`. Snapshot
     lands at `s3://bny-ddq-taxonomy-snapshots/tx_v0.1/snapshot.json`.
  6. Run DATA-PLAN §4.5 acceptance.

ADV is deferred to Day 8.5 per DATA-PLAN §1 ("BNY adviser subsidiary
identification — manual at first") + §8 step 05_parse_adv.py.

Run from repo root:
    .venv/bin/python data/bootstrap/09_build_taxonomy.py
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))                              # for core/, infra/
sys.path.insert(0, str(Path(__file__).parent))                  # for _lib

from _lib import MANIFESTS_DIR, s3_client  # noqa: E402

from core.domain.taxonomy import (  # noqa: E402
    CanonicalQuestion,
    FrameworkMapping,
)
from infra.adapters.mongo_taxonomy import MongoTaxonomy, SNAPSHOT_BUCKET  # noqa: E402

import torch  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.http import models as qm  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

# ── paths + constants ────────────────────────────────────────────
CAIQ_DATASET = REPO_ROOT / "data/sources/caiq/_extracted/ccm-machine-readable-bundle/CCMv4.0.12+CAIQv4.0.3-JSON-Dataset_Generated-at_2024-06-03/CAIQ/primary-dataset.json"
CCM_DATASET = REPO_ROOT / "data/sources/caiq/_extracted/ccm-machine-readable-bundle/CCMv4.0.12+CAIQv4.0.3-JSON-Dataset_Generated-at_2024-06-03/CCM/primary-dataset.json"
CCM_MAPPINGS_DIR = REPO_ROOT / "data/sources/caiq/_extracted/ccm-machine-readable-bundle/CCMv4.0.12+CAIQv4.0.3-JSON-Dataset_Generated-at_2024-06-03/CCM/mappings"
SPANS_FULL = MANIFESTS_DIR / "spans-full.json"
KEYS_DIR = REPO_ROOT / "data/manifests/keys"
SNAPSHOT_VERSION = "tx_v0.1"
QDRANT_COLL = "spans_v1"
SIM_THRESHOLD = 0.62

# CAIQ control-domain prefix → canonical hierarchy.
DOMAIN_MAP = {
    "A&A":  ("canon.is.audit",          "Audit & Assurance"),
    "AIS":  ("canon.is.appsec",         "Application & Interface Security"),
    "BCR":  ("canon.or.bcp",            "Business Continuity & Operational Resilience"),
    "CCC":  ("canon.is.change_control", "Change Control & Configuration Management"),
    "CEK":  ("canon.is.crypto",         "Cryptography, Encryption & Key Management"),
    "DCS":  ("canon.is.datacenter",     "Datacenter Security"),
    "DSP":  ("canon.is.data_security",  "Data Security & Privacy"),
    "GRC":  ("canon.reg.grc",           "Governance, Risk & Compliance"),
    "HRS":  ("canon.is.hr_security",    "Human Resources Security"),
    "IAM":  ("canon.is.iam",            "Identity & Access Management"),
    "IPY":  ("canon.is.interop",        "Interoperability & Portability"),
    "IVS":  ("canon.is.infra",          "Infrastructure & Virtualization Security"),
    "LOG":  ("canon.is.logging",        "Logging & Monitoring"),
    "SEF":  ("canon.cyber.incident",    "Security Incident Management & Forensics"),
    "STA":  ("canon.reg.supply_chain",  "Supply Chain Management & Transparency"),
    "TVM":  ("canon.cyber.vuln_mgmt",   "Threat & Vulnerability Management"),
    "UEM":  ("canon.is.endpoint",       "Universal Endpoint Management"),
}

CROSSWALK_FILES = {
    "NIST_SP800_53_rev5": ("rev5",  CCM_MAPPINGS_DIR / "NIST_800_53_rev5/mappings.json"),
    "ISO27001_2022":      ("2022",  CCM_MAPPINGS_DIR / "ISO27001_2022/mappings.json"),
    "PCI_DSS_v4.0":       ("v4.0",  CCM_MAPPINGS_DIR / "PCI_DSS_v4.0/mappings.json"),
    "AICPA_TSC_2017":     ("2017",  CCM_MAPPINGS_DIR / "AICPA_TSC_2017/mappings.json"),
    "NIST_CSF_v2.0":      ("v2.0",  CCM_MAPPINGS_DIR / "NIST_CSF_v2.0/mappings.json"),
}


# ── helpers ──────────────────────────────────────────────────────
def slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return s[:60] or "x"


def ccm_id_of(question_id: str) -> str:
    """A&A-01.1 → A&A-01"""
    return question_id.rsplit(".", 1)[0]


def domain_prefix(ccm_id: str) -> str:
    """A&A-01 → A&A"""
    return ccm_id.split("-", 1)[0]


def question_num(question_id: str) -> str:
    """A&A-01.1 → 1"""
    return question_id.rsplit(".", 1)[-1]


def label_from_text(text: str, n_words: int = 10) -> str:
    cleaned = " ".join(text.split())
    words = cleaned.split()
    out = " ".join(words[:n_words])
    if len(words) > n_words:
        out += "…"
    return out


def load_crosswalk() -> dict:
    """Returns: {ccm_id: {framework: [refs...]}} keyed across all 5 maps."""
    crosswalk: dict[str, dict[str, list[str]]] = defaultdict(dict)
    for fw, (ver, path) in CROSSWALK_FILES.items():
        if not path.exists():
            print(f"  warn: missing crosswalk file: {path.relative_to(REPO_ROOT)}")
            continue
        body = json.loads(path.read_text(encoding="utf-8"))
        items = body[0].get("mappings", []) if isinstance(body, list) and body else []
        for m in items:
            ccm = m.get("control_id")
            # Coerce to str — at least one PCI ref is encoded as a JSON float (3.6 for UEM-08).
            refs = [str(r) for r in (m.get("references") or []) if r is not None and r != ""]
            if ccm and refs:
                crosswalk[ccm][fw] = refs
    return crosswalk


def load_ccm_titles() -> dict:
    """Returns: {ccm_id: (title, specification)}"""
    out: dict[str, tuple[str, str]] = {}
    body = json.loads(CCM_DATASET.read_text(encoding="utf-8"))
    for domain in body.get("domains", []):
        for ctrl in domain.get("controls", []):
            cid = ctrl.get("id", "")
            out[cid] = (ctrl.get("title", "").strip(), ctrl.get("specification", "").strip())
    return out


# ── stage 1: CAIQ → canonical ────────────────────────────────────
def build_caiq_canonicals(crosswalk: dict, ccm_titles: dict) -> list[CanonicalQuestion]:
    body = json.loads(CAIQ_DATASET.read_text(encoding="utf-8"))
    questions = body.get("questions", [])
    canonicals: list[CanonicalQuestion] = []

    by_top_level: dict[str, str] = {}  # canon.is -> first child seen for parent_id seeding
    for q in questions:
        qid = q.get("id", "")
        cid = q.get("control_id", "") or ccm_id_of(qid)
        text = " ".join((q.get("body") or "").split())
        if not qid or not text:
            continue
        prefix = domain_prefix(cid)
        if prefix not in DOMAIN_MAP:
            print(f"  warn: unknown CAIQ domain prefix {prefix!r} on {qid}")
            continue
        sub_path, sub_label = DOMAIN_MAP[prefix]
        ccm_title, ccm_spec = ccm_titles.get(cid, ("", ""))

        canonical_id = f"{sub_path}.{slug(cid)}_q{question_num(qid)}"
        label = ccm_title or label_from_text(text, 8)
        description_parts = [text]
        if ccm_spec and ccm_spec.lower() != text.lower():
            description_parts.append(f"(CCM control specification: {ccm_spec})")
        description = " ".join(description_parts)

        # Framework mappings: CAIQ self + crosswalk by parent CCM id.
        fms: list[FrameworkMapping] = [
            FrameworkMapping(framework="CAIQ", version="v4.0.3", question_ref=qid),
        ]
        for fw, (ver, _) in CROSSWALK_FILES.items():
            for ref in crosswalk.get(cid, {}).get(fw, []):
                fms.append(FrameworkMapping(framework=fw, version=ver, question_ref=ref))

        # CCM also carries its own ref (the parent control).
        fms.append(FrameworkMapping(framework="CCM", version="v4.0.12", question_ref=cid))

        # parent_id: top-level (.is/.or/...) for now; SME can re-parent in M3.
        parent_id = sub_path

        canonicals.append(CanonicalQuestion(
            canonical_id=canonical_id,
            label=label,
            description=description,
            parent_id=parent_id,
            framework_mappings=fms,
            tier=2,
            owners=["bootstrap.seed"],
            tags=["bootstrap", "caiq-seeded"],
        ))
        by_top_level.setdefault(sub_path, canonical_id)

    return canonicals


# ── stage 2: AFME merge / extension ──────────────────────────────
AFME_SECTION_TO_TOP = [
    # ordered match — first hit wins
    (re.compile(r"\b(business continuity|disaster recovery|bcp|drp|operational resilience)\b", re.I), "canon.or.bcp"),
    (re.compile(r"\b(information security|cyber|encryption|access control|infosec)\b", re.I),         "canon.is.iam"),
    (re.compile(r"\b(audit|compliance|regulatory)\b", re.I),                                          "canon.reg.grc"),
    (re.compile(r"\b(anti.money.laundering|aml|kyc|sanctions|fatca)\b", re.I),                        "canon.reg.aml"),
    (re.compile(r"\b(tax|withholding)\b", re.I),                                                      "canon.reg.tax"),
    (re.compile(r"\b(esg|sustainability|climate|environmental|social|governance)\b", re.I),           "canon.esg.general"),
    (re.compile(r"\b(network|sub.?custody|local market|agent)\b", re.I),                              "canon.subc.network"),
    (re.compile(r"\b(account opening|account closure|kyc onboarding)\b", re.I),                       "canon.subc.account_lifecycle"),
    (re.compile(r"\b(corporate action|cash|income|reconciliation|settlement)\b", re.I),               "canon.or.operations"),
    (re.compile(r"\b(pricing|reporting|valuation)\b", re.I),                                          "canon.or.reporting"),
]
AFME_DEFAULT_TOP = "canon.subc.general"


def afme_top_for(item_text: str) -> str:
    for pat, top in AFME_SECTION_TO_TOP:
        if pat.search(item_text or ""):
            return top
    return AFME_DEFAULT_TOP


def gather_afme_questions() -> list[dict]:
    """Pull AFME spans whose anchor.subsection is set (i.e., real numbered questions)."""
    by_source = json.loads(SPANS_FULL.read_text(encoding="utf-8"))
    out: list[dict] = []
    for s in by_source.get("afme", []):
        anchor = s.get("anchor") or {}
        if anchor.get("kind") != "section":
            continue
        sub = anchor.get("subsection")
        if not sub:
            continue
        out.append({
            "span_id": s["span_id"],
            "doc_id": s["doc_id"],
            "text": s["text"],
            "subsection": sub,
            "item": anchor.get("item") or "",
        })
    return out


def merge_afme(
    canonicals: list[CanonicalQuestion],
    afme: list[dict],
    qdrant: QdrantClient,
    model: SentenceTransformer,
) -> tuple[list[CanonicalQuestion], dict]:
    """For each AFME question, find nearest CAIQ canonical via Qdrant on the
    span text. Above threshold → append mapping to existing canonical.
    Below → mint a new canon.* entry derived from AFME section context.
    """
    by_id = {c.canonical_id: c for c in canonicals}
    # Quick lookup: Qdrant is keyed on span_id; we want to map a CAIQ span_id
    # back to its canonical (since CAIQ span_id contains the question id).
    caiq_span_to_canonical: dict[str, str] = {}
    for c in canonicals:
        for m in c.framework_mappings:
            if m.framework == "CAIQ":
                # CAIQ span_id format from 03_parse_corpus: "caiq:v4.0.3:primary-dataset::CAIQ.<dom>.<qid>#0000"
                # For lookup we need the qid; record both candidate spans.
                qid = m.question_ref
                # Build the same section_id format used by parsers.caiq_json:
                domain_prefix_chars = qid.split("-", 1)[0]
                section_id = f"CAIQ.{domain_prefix_chars}.{qid}"
                caiq_span_to_canonical[f"caiq:v4.0.3:primary-dataset::{section_id}#0000"] = c.canonical_id

    stats = {"merged": 0, "new": 0, "skipped_low_text": 0, "below_threshold": 0,
             "by_new_top": defaultdict(int)}
    new_seen: dict[str, CanonicalQuestion] = {}

    BATCH = 32
    for i in range(0, len(afme), BATCH):
        chunk = afme[i:i + BATCH]
        texts = [q["text"] for q in chunk]
        # Skip very short / boilerplate text.
        usable_idx = [j for j, t in enumerate(texts) if len(t) > 25]
        if not usable_idx:
            stats["skipped_low_text"] += len(chunk)
            continue
        used_chunk = [chunk[j] for j in usable_idx]
        used_texts = [texts[j] for j in usable_idx]
        embeddings = model.encode(
            used_texts, batch_size=BATCH, normalize_embeddings=True,
            show_progress_bar=False, convert_to_numpy=True,
        )

        for q, emb in zip(used_chunk, embeddings):
            # Filter to only CAIQ source so we hit CAIQ canonicals.
            res = qdrant.query_points(
                collection_name=QDRANT_COLL, query=emb.tolist(), limit=1,
                query_filter=qm.Filter(must=[qm.FieldCondition(key="source", match=qm.MatchValue(value="caiq"))]),
                with_payload=True,
            ).points
            if not res:
                stats["below_threshold"] += 1
                _mint_new_afme(q, by_id, new_seen, stats)
                continue
            top = res[0]
            sim = top.score
            if sim < SIM_THRESHOLD:
                stats["below_threshold"] += 1
                _mint_new_afme(q, by_id, new_seen, stats)
                continue
            top_span_id = (top.payload or {}).get("span_id") or ""
            cid = caiq_span_to_canonical.get(top_span_id)
            if cid is None:
                stats["below_threshold"] += 1
                _mint_new_afme(q, by_id, new_seen, stats)
                continue
            # Append AFME mapping to existing canonical.
            target = by_id[cid]
            ref = f"AFME-{q['subsection']}"
            already = any(m.framework == "AFME" and m.question_ref == ref for m in target.framework_mappings)
            if not already:
                target.framework_mappings.append(
                    FrameworkMapping(framework="AFME", version="2026", question_ref=ref)
                )
                stats["merged"] += 1

    return canonicals + list(new_seen.values()), stats


def _mint_new_afme(q: dict, by_id: dict, new_seen: dict, stats: dict) -> None:
    """Create a new canonical entry for an AFME question that didn't match."""
    top = afme_top_for(q["item"])
    canonical_id = f"{top}.afme_{slug(q['subsection']).replace('_','')}"
    if canonical_id in by_id or canonical_id in new_seen:
        # Already minted (maybe two AFME variants land on same id) — append mapping.
        target = new_seen.get(canonical_id) or by_id[canonical_id]
        ref = f"AFME-{q['subsection']}"
        if not any(m.framework == "AFME" and m.question_ref == ref for m in target.framework_mappings):
            target.framework_mappings.append(
                FrameworkMapping(framework="AFME", version="2026", question_ref=ref)
            )
        return
    new_seen[canonical_id] = CanonicalQuestion(
        canonical_id=canonical_id,
        label=label_from_text(q["text"], 10),
        description=q["text"],
        parent_id=top,
        framework_mappings=[FrameworkMapping(framework="AFME", version="2026", question_ref=f"AFME-{q['subsection']}")],
        tier=2,
        owners=["bootstrap.seed"],
        tags=["bootstrap", "afme-seeded", afme_section_tag(q['item'])],
    )
    stats["new"] += 1
    stats["by_new_top"][top] += 1


def afme_section_tag(item_text: str) -> str:
    if not item_text:
        return "afme-section:unknown"
    first_word = re.sub(r"[^a-zA-Z]", "", item_text.split(">", 1)[0].strip())
    return f"afme-section:{first_word.lower() or 'unknown'}"


# ── stage 2b: NIST CSF 2.0 direct seed ───────────────────────────
def build_nist_csf_canonicals() -> list[CanonicalQuestion]:
    """One canonical per NIST CSF 2.0 subcategory.

    Function mapping (canonical hierarchy):
      GV (Govern)   → canon.reg.governance
      ID (Identify) → canon.cyber.identify
      PR (Protect)  → canon.cyber.protect
      DE (Detect)   → canon.cyber.detect
      RS (Respond)  → canon.cyber.respond
      RC (Recover)  → canon.cyber.recover
    """
    by_source = json.loads(SPANS_FULL.read_text(encoding="utf-8"))
    spans = by_source.get("nist_csf", [])
    function_map = {
        "GV": "canon.reg.governance",
        "ID": "canon.cyber.identify",
        "PR": "canon.cyber.protect",
        "DE": "canon.cyber.detect",
        "RS": "canon.cyber.respond",
        "RC": "canon.cyber.recover",
    }
    canonicals: list[CanonicalQuestion] = []
    seen_ids: set[str] = set()
    for s in spans:
        anchor = s.get("anchor") or {}
        if anchor.get("kind") != "structural":
            continue
        cid = anchor.get("path", "")
        # Filter to subcategories only (e.g., "ID.AM-01"); skip functions / categories.
        if not re.match(r"^[A-Z]{2}\.[A-Z]{2}-\d{2}", cid):
            continue
        family = cid.split(".", 1)[0]   # GV, ID, PR, DE, RS, RC
        top = function_map.get(family)
        if top is None:
            continue
        cid_slug = slug(cid)
        canonical_id = f"{top}.{cid_slug}"
        if canonical_id in seen_ids:
            continue
        seen_ids.add(canonical_id)
        text = s["text"]
        canonicals.append(CanonicalQuestion(
            canonical_id=canonical_id,
            label=label_from_text(text, 12),
            description=text,
            parent_id=top,
            framework_mappings=[
                FrameworkMapping(framework="NIST_CSF_v2.0", version="v2.0", question_ref=cid),
            ],
            tier=2,
            owners=["bootstrap.seed"],
            tags=["bootstrap", "nist-csf-seeded", "sig-candidate"],
        ))
    return canonicals


# ── stage 2c: AFME ESG direct seed ───────────────────────────────
def build_afme_esg_canonicals() -> list[CanonicalQuestion]:
    """Mint canon.esg.* entries from AFME HY ESG PDF — one per substantive paragraph."""
    by_source = json.loads(SPANS_FULL.read_text(encoding="utf-8"))
    spans = by_source.get("afme", [])
    out: list[CanonicalQuestion] = []
    seen: set[str] = set()
    for s in spans:
        prov = s.get("provenance") or {}
        extra = prov.get("extra") or {}
        if extra.get("variant") != "hy_esg":
            continue
        text = (s.get("text") or "").strip()
        # Take substantive paragraphs only.
        if len(text) < 220:
            continue
        anchor = s.get("anchor") or {}
        page = anchor.get("page") or 0
        # Use a content-derived hash slice for the canonical id leaf so
        # multiple paragraphs on the same page don't collide.
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
        canonical_id = f"canon.esg.afme_hy.p{page}_{h}"
        if canonical_id in seen:
            continue
        seen.add(canonical_id)
        out.append(CanonicalQuestion(
            canonical_id=canonical_id,
            label=label_from_text(text, 14),
            description=text,
            parent_id="canon.esg.afme_hy",
            framework_mappings=[
                FrameworkMapping(framework="AFME_ESG", version="2026-01", question_ref=f"AFME-HY-ESG-p{page}-{h}"),
            ],
            tier=2,
            owners=["bootstrap.seed"],
            tags=["bootstrap", "afme-esg-seeded", "scope:eu-hy"],
        ))
        if len(out) >= 60:   # cap; bootstrap-grade only
            break
    return out


# ── ed25519 dev key ──────────────────────────────────────────────
def ensure_dev_signing_key() -> tuple[bytes, str]:
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    priv_path = KEYS_DIR / "taxonomy_signing_dev.priv.pem"
    pub_path = KEYS_DIR / "taxonomy_signing_dev.pub.pem"
    if priv_path.exists():
        priv = serialization.load_pem_private_key(priv_path.read_bytes(), password=None)
    else:
        priv = Ed25519PrivateKey.generate()
        priv_path.write_bytes(priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        pub_path.write_bytes(priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        print(f"  generated dev signing key: {priv_path.relative_to(REPO_ROOT)} (DO NOT use in prod)")
    pem = priv_path.read_bytes()
    pub_pem = (priv if hasattr(priv, "public_key") else priv).public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH, format=serialization.PublicFormat.OpenSSH,
    ).decode()
    return pem, pub_pem


# ── main ─────────────────────────────────────────────────────────
def main() -> int:
    print("== Stage 1: CAIQ → canonical ==")
    crosswalk = load_crosswalk()
    ccm_titles = load_ccm_titles()
    print(f"  crosswalk: {len(crosswalk)} CCM controls with at least one mapping")
    print(f"  CCM titles: {len(ccm_titles)} controls")

    canonicals = build_caiq_canonicals(crosswalk, ccm_titles)
    print(f"  CAIQ canonicals minted: {len(canonicals)}")

    print("\n== Stage 2: AFME merge / extension ==")
    afme = gather_afme_questions()
    print(f"  AFME numbered questions: {len(afme)}")

    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer("BAAI/bge-small-en-v1.5", device=device)
    model.max_seq_length = 384
    qdrant = QdrantClient(url="http://localhost:6333", timeout=60)

    canonicals, stats = merge_afme(canonicals, afme, qdrant, model)

    print("\n== Stage 2b: NIST CSF 2.0 direct seed ==")
    csf_canonicals = build_nist_csf_canonicals()
    canonicals.extend(csf_canonicals)
    print(f"  NIST CSF canonicals minted: {len(csf_canonicals)}")

    print("\n== Stage 2c: AFME ESG direct seed ==")
    esg_canonicals = build_afme_esg_canonicals()
    canonicals.extend(esg_canonicals)
    print(f"  AFME ESG canonicals minted: {len(esg_canonicals)}")
    print(f"  merged into existing CAIQ: {stats['merged']}")
    print(f"  new canonicals from AFME : {stats['new']}")
    print(f"  skipped (short text)     : {stats['skipped_low_text']}")
    print(f"  below threshold {SIM_THRESHOLD}: {stats['below_threshold']}")
    print(f"  new by top-level domain  :")
    for top, n in sorted(stats["by_new_top"].items()):
        print(f"     {top:<28} {n}")

    print("\n== Stage 3: write to Mongo + cut signed snapshot ==")
    mongo = MongoClient("mongodb://ddq:ddq-dev@localhost:27018", serverSelectionTimeoutMS=5000)
    s3 = s3_client()
    svc = MongoTaxonomy(mongo, s3)

    # Wipe-and-rebuild for idempotency.
    svc.coll.delete_many({})
    t0 = time.time()
    for c in canonicals:
        svc.upsert(c)
    print(f"  upserted: {len(canonicals)}  in {time.time() - t0:.1f}s")

    priv_pem, _ = ensure_dev_signing_key()
    snap = svc.cut_version(SNAPSHOT_VERSION, signer_id="dev.bootstrap@local", signer_priv_key_pem=priv_pem)
    print(f"  snapshot {SNAPSHOT_VERSION} sealed:")
    print(f"     question_count={snap.question_count}")
    print(f"     merkle_root={snap.merkle_root}")
    print(f"     signed_by={snap.signed_by}")
    print(f"     framework_coverage={dict(snap.framework_coverage)}")

    print("\n== Stage 4: DATA-PLAN §4.5 acceptance ==")
    domains = defaultdict(int)
    has_non_self_mapping = 0
    caiq_total = 0
    for c in canonicals:
        top = ".".join(c.canonical_id.split(".")[:2])  # canon.is / canon.or / ...
        domains[top] += 1
        non_self = {m.framework for m in c.framework_mappings if m.framework != "CAIQ"}
        is_caiq = any(m.framework == "CAIQ" for m in c.framework_mappings)
        if is_caiq:
            caiq_total += 1
            if non_self:
                has_non_self_mapping += 1

    coverage_pass = (len(canonicals) >= 400) and (len(domains) >= 6 - 0)  # 6 top-level groups expected
    mapping_density = (has_non_self_mapping / caiq_total) if caiq_total else 0.0
    mapping_pass = mapping_density >= 0.95

    # Snapshot integrity: re-load + verify merkle root.
    reload = svc.load_snapshot(SNAPSHOT_VERSION)
    integrity_pass = reload.merkle_root == snap.merkle_root and reload.question_count == snap.question_count

    # Round-trip: pick 5 random canonical_ids, fetch via versioned get.
    import random
    rng = random.Random(20260510)
    sample_ids = rng.sample([c.canonical_id for c in canonicals], min(5, len(canonicals)))
    roundtrip_failures = []
    for cid in sample_ids:
        live = svc.get(cid)
        snapshot_pull = svc.get(cid, version=SNAPSHOT_VERSION)
        if live is None or snapshot_pull is None:
            roundtrip_failures.append({"cid": cid, "live": live is not None, "snapshot": snapshot_pull is not None})
            continue
        if live.to_canonical_dict() != snapshot_pull.to_canonical_dict():
            roundtrip_failures.append({"cid": cid, "diff": True})
    roundtrip_pass = not roundtrip_failures

    print(f"  domains seen ({len(domains)}):")
    for d, n in sorted(domains.items()):
        print(f"     {d:<28} {n}")
    flag = lambda b: "PASS" if b else "FAIL"
    print(f"  AC#1 coverage  (≥400 IDs / ≥6 top-levels)            : {flag(coverage_pass)}  ({len(canonicals)} IDs / {len(domains)} top-levels)")
    print(f"  AC#2 mapping density (≥95% CAIQ have non-self map)   : {flag(mapping_pass)}  ({mapping_density:.1%})")
    print(f"  AC#3 snapshot integrity (merkle re-load matches)     : {flag(integrity_pass)}")
    print(f"  AC#4 round-trip get(cid, version=tx_v0.1)            : {flag(roundtrip_pass)}  ({len(sample_ids)} sampled)")

    report = {
        "version": SNAPSHOT_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "merkle_root": snap.merkle_root,
        "signed_by": snap.signed_by,
        "question_count": snap.question_count,
        "framework_coverage": dict(snap.framework_coverage),
        "domains": dict(domains),
        "afme_merge_stats": {**stats, "by_new_top": dict(stats["by_new_top"])},
        "acceptance": {
            "ac1_coverage": coverage_pass,
            "ac2_mapping_density": {"pass": mapping_pass, "value": mapping_density,
                                    "caiq_with_non_self": has_non_self_mapping, "caiq_total": caiq_total},
            "ac3_integrity": integrity_pass,
            "ac4_roundtrip": {"pass": roundtrip_pass, "failures": roundtrip_failures},
        },
    }
    out_path = MANIFESTS_DIR / "taxonomy-v0.1-report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nreport: {out_path.relative_to(REPO_ROOT)}")
    print(f"snapshot: s3://{SNAPSHOT_BUCKET}/{SNAPSHOT_VERSION}/snapshot.json")

    overall = coverage_pass and mapping_pass and integrity_pass and roundtrip_pass
    print(f"\noverall: {flag(overall)}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
