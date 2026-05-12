"""
Seed a small fs-mode canonical manifest at
$REPO/data/manifests/canonical/<canonical_id>.json so the datasets UI
has something to render without needing LocalStack S3 / Mongo.

Pulls 12 representative canonicals from the same domain map
`09_build_taxonomy.py` uses. Idempotent — re-running overwrites the
files.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data" / "manifests" / "canonical"


SEED = [
    ("canon.is.iam.iam_04_q1", "Multi-factor authentication for privileged access",
     "Are multi-factor authentication mechanisms required for all privileged users accessing production systems?",
     None, 1, "infosec",
     [("CAIQ", "v4.0.3", "IAM-04.1"),
      ("NIST_SP800_53_rev5", "rev5", "IA-2(1)"),
      ("ISO27001_2022", "2022", "A.8.5")]),
    ("canon.is.iam.iam_05_q1", "User access review cadence",
     "How frequently are user access rights reviewed and reauthorized for privileged accounts?",
     "canon.is.iam", 2, "infosec",
     [("CAIQ", "v4.0.3", "IAM-05.1"),
      ("NIST_SP800_53_rev5", "rev5", "AC-2(j)")]),
    ("canon.cyber.protect.pr_aa_01", "Identity assertion and authentication",
     "Identities and credentials for authorized users, services, and hardware are managed by the organization.",
     None, 1, "cyber",
     [("NIST_CSF_v2.0", "v2.0", "PR.AA-01")]),
    ("canon.cyber.detect.de_cm_01", "Continuous network monitoring",
     "Network monitoring detects potentially adverse events.",
     None, 2, "cyber",
     [("NIST_CSF_v2.0", "v2.0", "DE.CM-01")]),
    ("canon.or.bcp.bcr_01_q1", "Business continuity plan testing",
     "How often is the business continuity plan tested end-to-end?",
     "canon.or.bcp", 1, "ops-risk",
     [("CAIQ", "v4.0.3", "BCR-01.1"),
      ("AFME", "2026", "AFME-OR-7.3")]),
    ("canon.reg.governance.afme_4_1", "Board oversight of risk",
     "Describe the board's oversight role for enterprise risk management.",
     None, 1, "legal",
     [("AFME", "2026", "AFME-4.1")]),
    ("canon.reg.audit.afme_6_2", "Internal audit function independence",
     "Confirm the internal audit function reports independently to the audit committee.",
     "canon.reg.audit", 2, "legal",
     [("AFME", "2026", "AFME-6.2")]),
    ("canon.esg.governance.afme_esg_3_1", "ESG governance structure",
     "Describe the governance structure responsible for ESG-related risks and opportunities.",
     None, 2, "esg",
     [("AFME_ESG", "2026", "AFME-ESG-3.1")]),
    ("canon.subc.vendor.tpr_01_q1", "Third-party risk assessment cadence",
     "What is the frequency and scope of third-party risk assessments for critical vendors?",
     "canon.subc.vendor", 1, "tprm",
     [("CAIQ", "v4.0.3", "STA-08.1"),
      ("AFME", "2026", "AFME-SUBC-3.1")]),
    ("canon.is.dsi.dsi_03_q1", "Encryption at rest",
     "Is sensitive client data encrypted at rest using approved cryptographic standards?",
     "canon.is.dsi", 1, "infosec",
     [("CAIQ", "v4.0.3", "DSI-03.1"),
      ("NIST_SP800_53_rev5", "rev5", "SC-28")]),
    ("canon.is.dsi.dsi_04_q1", "Encryption in transit",
     "Is sensitive client data encrypted in transit using TLS 1.2+ or equivalent?",
     "canon.is.dsi", 1, "infosec",
     [("CAIQ", "v4.0.3", "DSI-04.1"),
      ("NIST_SP800_53_rev5", "rev5", "SC-8(1)")]),
    ("canon.or.incident.afme_or_5_4", "Incident notification SLA",
     "What is the SLA for notifying clients of a material security incident?",
     None, 1, "legal",
     [("AFME", "2026", "AFME-OR-5.4")]),
]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ts = now_iso()
    for cid, label, desc, parent, tier, owner, mappings in SEED:
        body = {
            "canonical_id": cid,
            "label": label,
            "description": desc,
            "parent_id": parent,
            "framework_mappings": [
                {"framework": fw, "version": v, "question_ref": ref}
                for fw, v, ref in mappings
            ],
            "tier": tier,
            "do_not_answer": False,
            "owners": [owner],
            "tags": ["bootstrap"],
            "created_at": ts,
            "updated_at": ts,
            "synonyms_embedding": None,
        }
        (OUT / f"{cid}.json").write_text(
            json.dumps(body, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(f"Wrote {len(SEED)} canonical entries to {OUT}")


if __name__ == "__main__":
    main()
