"""
Pure-domain types for the canonical taxonomy. No I/O, no external deps.
Mirrors `docs/ddq.md` §L05. Stays compatible with Pydantic in M1.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Optional

CanonicalId = str
TaxonomyVersion = str


@dataclass(frozen=True)
class FrameworkMapping:
    framework: str        # e.g., "AFME" | "CAIQ" | "NIST_SP800_53_rev5" | "ISO27001_2022"
    version: str          # e.g., "v4.0.3" | "rev5" | "2022"
    question_ref: str     # e.g., "AFME-IS-3.4" | "IAM-04" | "AC-2"


@dataclass
class CanonicalQuestion:
    canonical_id: CanonicalId
    label: str
    description: str
    parent_id: Optional[CanonicalId]
    framework_mappings: list[FrameworkMapping] = field(default_factory=list)
    synonyms_embedding: Optional[str] = None         # Qdrant point id (filled in by indexer)
    tier: int = 2                                    # 1=high-risk, 2=std, 3=low
    do_not_answer: bool = False
    owners: list[str] = field(default_factory=lambda: ["bootstrap.seed"])
    tags: list[str] = field(default_factory=lambda: ["bootstrap"])
    created_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())

    def to_canonical_dict(self) -> dict:
        """Stable serialization for hashing / signing.

        Excludes mutable timestamps and the Qdrant pointer; framework_mappings
        sort-stable. Adding new fields requires bumping snapshot version.
        """
        d = {
            "canonical_id": self.canonical_id,
            "label": self.label,
            "description": self.description,
            "parent_id": self.parent_id,
            "framework_mappings": sorted(
                [asdict(m) for m in self.framework_mappings],
                key=lambda m: (m["framework"], m["version"], m["question_ref"]),
            ),
            "tier": self.tier,
            "do_not_answer": self.do_not_answer,
            "owners": sorted(self.owners),
            "tags": sorted(self.tags),
        }
        return d

    def content_hash(self) -> str:
        body = json.dumps(self.to_canonical_dict(), sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass
class TaxonomySnapshot:
    """Sealed snapshot per ddq.md §L05; one of these gets uploaded to S3 with Object Lock."""
    version: TaxonomyVersion
    cut_at: str
    question_count: int
    framework_coverage: dict[str, int]
    merkle_root: str
    signed_by: str
    signature: str           # ed25519 signature of merkle_root
    questions: list[dict]    # list of CanonicalQuestion.to_canonical_dict() outputs


def merkle_root(content_hashes: list[str]) -> str:
    """Pairwise SHA-256 Merkle tree (Bitcoin-style; duplicates last when odd)."""
    if not content_hashes:
        return "sha256:" + hashlib.sha256(b"").hexdigest()
    layer = [bytes.fromhex(h.removeprefix("sha256:")) for h in sorted(content_hashes)]
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [
            hashlib.sha256(layer[i] + layer[i + 1]).digest()
            for i in range(0, len(layer), 2)
        ]
    return "sha256:" + layer[0].hex()
