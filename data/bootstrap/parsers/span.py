"""
Evidence span schema — pure-Python mirror of the Pydantic model in
ddq.md §L03. Used by every parser and by the parquet writer; no I/O.

Anchors per DATA-PLAN §3.5:
    PageAnchor    — {kind="page", page, doc_hash}                 # PDFs
    SectionAnchor — {kind="section", item, subsection, doc_hash}  # structured filings, DOCX
We extend with one more variant for catalogued data:
    StructuralAnchor — {kind="structural", path, doc_hash}        # CAIQ JSON / OSCAL
where `path` is e.g. "AAC-01.1" (control_id + question number).

`span_hash` is `sha256:<hex>` of `text.encode('utf-8')`. `doc_hash` is
`sha256:<hex>` of the raw source bytes (already in knowledge-documents.json).
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Literal, Optional, Union


def text_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PageAnchor:
    page: int
    doc_hash: str
    kind: Literal["page"] = "page"


@dataclass(frozen=True)
class SectionAnchor:
    item: str
    doc_hash: str
    subsection: Optional[str] = None
    kind: Literal["section"] = "section"


@dataclass(frozen=True)
class StructuralAnchor:
    path: str
    doc_hash: str
    kind: Literal["structural"] = "structural"


Anchor = Union[PageAnchor, SectionAnchor, StructuralAnchor]


@dataclass(frozen=True)
class Provenance:
    source: str                 # "edgar" | "bny-ir" | "afme" | "caiq" | "nist" | ...
    parser: str                 # "edgar_html@1" | "pymupdf@1" | "python-docx@1" | "caiq_json@1"
    ingested_at: str            # RFC3339
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Span:
    doc_id: str
    doc_hash: str
    section_id: str
    span_id: str
    span_hash: str
    text: str
    anchor: dict                # asdict(PageAnchor|SectionAnchor|StructuralAnchor)
    provenance: dict            # asdict(Provenance)

    def to_dict(self) -> dict:
        return asdict(self)


def make_span(
    doc_id: str,
    doc_hash: str,
    section_id: str,
    ordinal: int,
    text: str,
    anchor: Anchor,
    provenance: Provenance,
) -> Span:
    """Build a Span with deterministic globally-unique span_id and
    content-addressed span_hash.

    span_id format: `{doc_id}::{section_id}#{ordinal:04d}` — stable across
    re-parses and unique across the whole corpus (doc_id is unique per doc).
    """
    sh = text_hash(text)
    return Span(
        doc_id=doc_id,
        doc_hash=doc_hash,
        section_id=section_id,
        span_id=f"{doc_id}::{section_id}#{ordinal:04d}",
        span_hash=sh,
        text=text,
        anchor=asdict(anchor),
        provenance=asdict(provenance),
    )
