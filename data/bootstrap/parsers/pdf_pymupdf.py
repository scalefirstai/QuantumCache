"""
PDF parser — Pillar 3 quarterly reports + AFME ESG.

Uses PyMuPDF (fitz). One span per paragraph; PageAnchor carries the page
number. Section-level structure is best-effort heading detection: the first
line on a page starting in a >12pt font is treated as the section heading
for spans on that page (recorded as anchor.subsection-equivalent in the
section_id). For the citation guardrail, page-level anchors are sufficient.

Anchors strategy (DATA-PLAN §9 risk #5): page-level anchors are unstable
across re-uploads when paginated content shifts. We mitigate by also
recording the heading text in section_id so a re-pagination can still match
on heading.
"""

from __future__ import annotations

import datetime as dt
import io
import re
from typing import Iterable

import fitz  # PyMuPDF

from .span import (
    PageAnchor,
    Provenance,
    Span,
    make_span,
)

PARSER_VERSION = "pymupdf@1"

MAX_SPAN_CHARS = 2000
MIN_SPAN_CHARS = 30          # drop noise (page numbers, single words)
HEADING_FONTSIZE_THRESHOLD = 12.5


def _heading_for_page(page: "fitz.Page") -> str | None:
    """First line on the page in font size >= threshold."""
    try:
        d = page.get_text("dict")
    except Exception:
        return None
    for block in d.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            first = spans[0]
            text = (first.get("text") or "").strip()
            if not text or len(text) < 3:
                continue
            if first.get("size", 0) >= HEADING_FONTSIZE_THRESHOLD:
                # Cap heading length and slug-ify for section_id.
                return text[:80]
    return None


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_")
    return s[:60] or "Section"


def _split_paragraphs(page_text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", page_text) if p.strip()]
    out: list[str] = []
    for p in paras:
        # Collapse intra-paragraph single newlines.
        p = re.sub(r"\s*\n\s*", " ", p)
        p = re.sub(r"\s{2,}", " ", p)
        if len(p) < MIN_SPAN_CHARS:
            continue
        if len(p) <= MAX_SPAN_CHARS:
            out.append(p)
            continue
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", p)
        buf = ""
        for s in sentences:
            if len(buf) + len(s) + 1 > MAX_SPAN_CHARS and buf:
                out.append(buf.strip())
                buf = s
            else:
                buf = (buf + " " + s).strip() if buf else s
        if buf.strip():
            out.append(buf.strip())
    return out


def parse_pdf(
    *,
    body: bytes,
    doc_id: str,
    doc_hash: str,
    source: str,
    extra: dict | None = None,
) -> Iterable[Span]:
    provenance = Provenance(
        source=source,
        parser=PARSER_VERSION,
        ingested_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        extra=extra or {},
    )

    with fitz.open(stream=io.BytesIO(body), filetype="pdf") as doc:
        # `current_section` carries the most recent heading we've seen.
        current_section = "Section_Front"
        current_section_ordinal = 0   # global counter within section
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            heading = _heading_for_page(page)
            if heading:
                slug = _slug(heading)
                # New heading → new section, reset ordinal.
                if slug != current_section:
                    current_section = slug
                    current_section_ordinal = 0

            page_text = page.get_text("text") or ""
            paras = _split_paragraphs(page_text)
            for txt in paras:
                anchor = PageAnchor(page=page_idx + 1, doc_hash=doc_hash)
                yield make_span(
                    doc_id=doc_id,
                    doc_hash=doc_hash,
                    section_id=f"{current_section}.p{page_idx+1}",
                    ordinal=current_section_ordinal,
                    text=txt,
                    anchor=anchor,
                    provenance=provenance,
                )
                current_section_ordinal += 1
