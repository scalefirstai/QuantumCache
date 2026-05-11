"""
EDGAR HTML parser — 10-K / 10-Q / 8-K / DEF 14A.

Strategy:
  1. Strip <script>, <style>, navigation furniture; collapse to plain text.
  2. Split on Item/PART boundaries (first occurrence past a content threshold
     skips TOC noise).
  3. Within each section, split into spans on paragraph boundaries; spans
     >2KB are sentence-split.
  4. Section anchors carry (item, subsection|None, doc_hash).

Anchor stability strategy (DATA-PLAN §9 risk #5): we anchor on Items, not
pages, because EDGAR re-uploads can shift inline formatting but Items are
fixed by the filing structure.
"""

from __future__ import annotations

import datetime as dt
import re
import warnings
from typing import Iterable

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .span import (
    SectionAnchor,
    Provenance,
    Span,
    make_span,
)

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

PARSER_VERSION = "edgar_html@1"

MAX_SPAN_CHARS = 2000

# 10-K, 10-Q, 8-K — both ITEM/Item, with optional PART prefix carried in
# the surrounding context. We capture the item designator (e.g., "1A", "7",
# "8.01") and use first-occurrence-after-content-threshold to skip TOC.
ITEM_RE = re.compile(r"(?im)^\s*(?:ITEM|Item)\s+([0-9]+(?:\.[0-9]+|[A-Z])?)\s*[.\-:\s]")
PART_RE = re.compile(r"(?im)^\s*(?:PART|Part)\s+(I{1,3}V?|IV)\b")
DEF14A_PROPOSAL_RE = re.compile(r"(?im)^\s*(?:ITEM|Item)\s+([0-9]+(?:\.[0-9]+)?)\s*[—–\-]\s*([A-Z][A-Z0-9 ,&'\-]{4,80})")

# A page of dense text is ~3000 chars. Real content typically starts after
# the cover page + TOC, ~5% in. Skip the first 1500 chars when looking for
# section starts to avoid TOC matches.
TOC_SKIP_CHARS = 1500


def _to_text(html: bytes) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "iframe"]):
        tag.decompose()
    # `\n` separator preserves line structure; we collapse runs later.
    text = soup.get_text("\n", strip=True)
    # Normalize non-breaking spaces and other whitespace.
    text = text.replace("\xa0", " ").replace("​", "")
    # Collapse 3+ blank lines to 2.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _find_section_boundaries(text: str, form: str) -> list[tuple[int, str]]:
    """Return [(char_offset, section_id), ...] sorted by offset.

    section_id is form-specific:
      10-K, 10-Q: "Item_<num>" with PART prefix where applicable
      8-K:        "Item_<n>.<nn>"
      DEF 14A:    "Item_<num>" (proposal numbering)
    """
    out: list[tuple[int, str]] = []
    seen_items: set[str] = set()

    # Track current PART context so 10-Q sections get "PART_II.Item_1"
    current_part: str | None = None
    part_iter = list(PART_RE.finditer(text))
    item_iter = list(ITEM_RE.finditer(text))

    # Merge sort PART + Item events by char offset.
    events: list[tuple[int, str, str]] = []  # (offset, kind, payload)
    for m in part_iter:
        events.append((m.start(), "part", m.group(1).upper()))
    for m in item_iter:
        events.append((m.start(), "item", m.group(1).upper()))
    events.sort(key=lambda e: e[0])

    for offset, kind, payload in events:
        if kind == "part":
            current_part = payload
            continue
        # First occurrence of an Item only, and only past the TOC skip.
        if offset < TOC_SKIP_CHARS:
            continue
        item_key = payload
        # For 10-Q, distinguish Part I Item 1 from Part II Item 1.
        if form == "10-Q" and current_part:
            item_key = f"{current_part}.{item_key}"
        if item_key in seen_items:
            continue
        seen_items.add(item_key)
        section_id = f"PART_{current_part}.Item_{payload}" if (form == "10-Q" and current_part) else f"Item_{payload}"
        out.append((offset, section_id))

    out.sort()
    return out


def _split_into_spans(section_text: str) -> list[str]:
    """Paragraph-split, then sentence-split anything over MAX_SPAN_CHARS."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", section_text) if p.strip()]
    out: list[str] = []
    for p in paragraphs:
        if len(p) <= MAX_SPAN_CHARS:
            out.append(p)
            continue
        # Sentence split (cheap heuristic — good enough for English filings).
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


def parse_edgar_html(
    *,
    body: bytes,
    doc_id: str,
    doc_hash: str,
    form: str,
    filing_date: str,
    accession: str,
) -> Iterable[Span]:
    text = _to_text(body)
    if not text.strip():
        return

    boundaries = _find_section_boundaries(text, form)

    # Emit a "preamble" pseudo-section for content before the first Item.
    if not boundaries:
        sections = [("Whole_Document", text)]
    else:
        first_start = boundaries[0][0]
        sections: list[tuple[str, str]] = []
        if first_start > 0:
            preamble = text[:first_start].strip()
            if preamble:
                sections.append(("Preamble", preamble))
        for i, (start, sid) in enumerate(boundaries):
            end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
            chunk = text[start:end].strip()
            if chunk:
                sections.append((sid, chunk))

    provenance = Provenance(
        source="edgar",
        parser=PARSER_VERSION,
        ingested_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        extra={"form": form, "filing_date": filing_date, "accession": accession},
    )

    for section_id, section_text in sections:
        spans = _split_into_spans(section_text)
        for ordinal, txt in enumerate(spans):
            anchor = SectionAnchor(item=section_id, doc_hash=doc_hash)
            yield make_span(
                doc_id=doc_id,
                doc_hash=doc_hash,
                section_id=section_id,
                ordinal=ordinal,
                text=txt,
                anchor=anchor,
                provenance=provenance,
            )
