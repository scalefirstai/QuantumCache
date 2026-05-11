"""
Pure-domain types for the answer library — ddq.md §L04. No I/O.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Optional


EntryId = str
ProposalId = str


@dataclass(frozen=True)
class LibraryKey:
    canonical_id: str
    entity: str
    product: Optional[str] = None


@dataclass(frozen=True)
class EvidenceRef:
    doc_hash: str          # "sha256:<hex>"
    span_hash: str         # "sha256:<hex>"
    anchor: dict           # PageAnchor / SectionAnchor / StructuralAnchor (serialized)
    doc_id: Optional[str] = None
    span_id: Optional[str] = None
    score: Optional[float] = None
    excerpt: Optional[str] = None


@dataclass(frozen=True)
class Approver:
    user_id: str
    role: str
    ts: str
    comment: str = ""


@dataclass
class LibraryEntry:
    entry_id: EntryId
    canonical_id: str
    entity: str
    product: Optional[str]
    answer_text: str
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    approvers: list[Approver] = field(default_factory=list)
    effective_date: str = ""             # ISO date
    expiry_date: Optional[str] = None
    review_due: Optional[str] = None
    version: int = 1
    supersedes: Optional[EntryId] = None
    tags: list[str] = field(default_factory=lambda: ["bootstrap"])
    do_not_answer: bool = False
    created_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())

    def to_canonical_dict(self) -> dict:
        """Stable serialization for hashing — excludes timestamps."""
        return {
            "entry_id": self.entry_id,
            "canonical_id": self.canonical_id,
            "entity": self.entity,
            "product": self.product,
            "answer_text": self.answer_text,
            "evidence_refs": sorted(
                [asdict(e) for e in self.evidence_refs],
                key=lambda e: (e.get("doc_hash") or "", e.get("span_hash") or ""),
            ),
            "approvers": sorted(
                [asdict(a) for a in self.approvers],
                key=lambda a: (a.get("ts") or "", a.get("user_id") or ""),
            ),
            "effective_date": self.effective_date,
            "expiry_date": self.expiry_date,
            "review_due": self.review_due,
            "version": self.version,
            "supersedes": self.supersedes,
            "tags": sorted(self.tags),
            "do_not_answer": self.do_not_answer,
        }

    def content_hash(self) -> str:
        body = json.dumps(self.to_canonical_dict(), sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass
class LibrarySnapshot:
    """Sealed library snapshot — written to S3 Object Lock."""
    version: str                         # "lib_v0.1"
    cut_at: str
    entry_count: int
    by_entity: dict[str, int]
    merkle_root: str
    signed_by: str
    signature: str
    entries: list[dict]                  # entry.to_canonical_dict() outputs
