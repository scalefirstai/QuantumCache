"""
CAIQ + CCM JSON normalizer.

CSA's machine-readable bundle ships:
  CAIQ/primary-dataset.json    — { name, version, questions: [{id, control_id, body}, ...] }
  CCM/primary-dataset.json     — { name, version, controls: [{id, title, specification, ...}, ...] }
  CCM/mappings/<framework>/mappings.json  — list of {ccm_id, mapped_ids, ...}

We emit one Span per CAIQ question and one Span per CCM control, anchored
on the structural id (e.g., "A&A-01.1" or "A&A-01"). These spans are the
seed of the canonical taxonomy (Day 8 in DATA-PLAN §8) — they're indexed
into retrieval today so L05's classify-by-embedding has training-time
candidates.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Iterable

from .span import (
    Provenance,
    Span,
    StructuralAnchor,
    make_span,
)

PARSER_VERSION = "caiq_json@1"


def _provenance(source: str, version: str | None, extra: dict | None = None) -> Provenance:
    return Provenance(
        source=source,
        parser=PARSER_VERSION,
        ingested_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        extra={"version": version, **(extra or {})},
    )


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def parse_caiq_questions(
    *,
    body: bytes,
    doc_id: str,
    doc_hash: str,
) -> Iterable[Span]:
    data = json.loads(body)
    version = data.get("version")
    prov = _provenance("caiq", version, {"dataset": data.get("name")})
    for q in data.get("questions", []):
        qid = q.get("id", "")
        cid = q.get("control_id", "")
        text = _norm(q.get("body", ""))
        if not text:
            continue
        # section_id: control domain (everything before the first hyphen).
        # Use the question id (e.g., "A&A-01.1"), not the control id, since
        # multiple questions share a control id and would otherwise collide.
        domain = cid.split("-")[0] if "-" in cid else (qid.split("-")[0] if qid else "CAIQ")
        section_id = f"CAIQ.{domain}.{qid}" if qid else f"CAIQ.{cid}"
        anchor = StructuralAnchor(path=qid, doc_hash=doc_hash)
        yield make_span(
            doc_id=doc_id,
            doc_hash=doc_hash,
            section_id=section_id,
            ordinal=0,        # one span per question
            text=text,
            anchor=anchor,
            provenance=prov,
        )


def parse_ccm_controls(
    *,
    body: bytes,
    doc_id: str,
    doc_hash: str,
) -> Iterable[Span]:
    """CSA CCM JSON shape (v4.0.12 dataset):
        { name, version, url, domains: [{id, title, controls: [{id, title, specification, ...}]}] }
    """
    data = json.loads(body)
    version = data.get("version")
    prov = _provenance("ccm", version, {"dataset": data.get("name")})
    for domain in data.get("domains", []):
        d_id = domain.get("id", "")
        d_title = domain.get("title", "")
        for c in domain.get("controls", []):
            cid = c.get("id", "")
            title = _norm(c.get("title", ""))
            spec = _norm(c.get("specification", ""))
            text = f"{title}. {spec}" if title and spec else (title or spec)
            if not text:
                continue
            section_id = f"CCM.{d_id}.{cid}" if d_id else f"CCM.{cid}"
            anchor = StructuralAnchor(path=cid, doc_hash=doc_hash)
            yield make_span(
                doc_id=doc_id,
                doc_hash=doc_hash,
                section_id=section_id,
                ordinal=0,
                text=text,
                anchor=anchor,
                provenance=Provenance(
                    source="ccm",
                    parser=PARSER_VERSION,
                    ingested_at=prov.ingested_at,
                    extra={**prov.extra, "domain_id": d_id, "domain_title": d_title},
                ),
            )


def parse_oscal_catalog(
    *,
    body: bytes,
    doc_id: str,
    doc_hash: str,
    source: str,
    framework: str,
) -> Iterable[Span]:
    """NIST OSCAL catalog → spans per control.

    `source` is the data-source family ("nist_csf" | "nist_800_53"); `framework`
    is the human label baked into section_id and provenance.extra.

    OSCAL catalog shape: { catalog: { groups: [{ controls: [...] }, ...] } }
    Each control: { id, title, parts: [{ name: "statement", prose: "..." }, ...] }
    """
    data = json.loads(body)
    catalog = data.get("catalog", {})
    version = (catalog.get("metadata") or {}).get("version")
    prov = _provenance(source, version, {"catalog_id": catalog.get("uuid"), "framework": framework})

    def walk_groups(groups, group_path):
        for g in groups or []:
            g_title = g.get("title", "")
            new_path = group_path + [g_title] if g_title else group_path
            for ctrl in g.get("controls", []) or []:
                yield from walk_control(ctrl, new_path)
            yield from walk_groups(g.get("groups"), new_path)

    def walk_control(ctrl, group_path):
        cid = ctrl.get("id", "")
        title = _norm(ctrl.get("title", ""))
        # Collect statement parts; OSCAL nests them.
        prose_parts: list[str] = []
        for part in ctrl.get("parts", []) or []:
            p = _norm(part.get("prose", ""))
            if p:
                prose_parts.append(p)
        text = ". ".join([t for t in [title, *prose_parts] if t])
        if not text:
            # Sub-controls/enhancements may carry only sub-parts; skip empty.
            return
        section_id = f"{framework}.{'/'.join(group_path)}.{cid}" if group_path else f"{framework}.{cid}"
        anchor = StructuralAnchor(path=cid, doc_hash=doc_hash)
        yield make_span(
            doc_id=doc_id,
            doc_hash=doc_hash,
            section_id=section_id,
            ordinal=0,
            text=text,
            anchor=anchor,
            provenance=prov,
        )
        # Recurse into enhancements (sub-controls).
        for sub in ctrl.get("controls", []) or []:
            yield from walk_control(sub, group_path)

    yield from walk_groups(catalog.get("groups"), [])
