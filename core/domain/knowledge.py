"""
Pure-domain type for a knowledge-corpus document — ddq.md §L03.

A `KnowledgeDocument` is the metadata record for a single source file
sitting in `s3://bny-ddq-knowledge-raw/...` (filings, framework docs,
Pillar 3 disclosures). The bytes themselves are content-addressed by
`doc_hash`; metadata is mutable (tags, descriptions, effective dates)
without invalidating the hash.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from typing import Optional


DocId = str


@dataclass
class KnowledgeDocument:
    doc_id: DocId
    source: str                                  # "edgar" | "bny-ir" | "afme" | "caiq" | "nist" | ...
    entity: str                                  # "bny-mellon-corp" | "framework"
    primary_desc: str
    doc_hash: str                                # "sha256:<hex>" — content address, immutable
    content_type: str
    bytes: int
    s3_uri: str
    ingested_at: str
    tags: list[str] = field(default_factory=list)
    kind: Optional[str] = None                   # "10-K" | "pillar3" | "framework" | ...
    effective_date: Optional[str] = None         # ISO date
    url: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def display_title(self) -> str:
        bits = [self.entity, self.kind or "", self.primary_desc or ""]
        return " · ".join(b for b in bits if b)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
