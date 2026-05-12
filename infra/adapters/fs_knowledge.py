"""
Filesystem-backed KnowledgeRepository.

Storage layout:

  $manifests/knowledge-documents.json   — JSON array of doc records
                                          (the same shape Day 3–4 bootstrap
                                          writes; this adapter keeps it
                                          updatable).

All writes go through a tmp-file + os.replace to make crashes atomic.
The bytes themselves live in S3 (`bny-ddq-knowledge-raw/...`) and are
content-addressed; this adapter touches only the metadata.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import fields
from pathlib import Path
from typing import Iterator, Optional

from core.domain.knowledge import DocId, KnowledgeDocument, now_iso


class FsKnowledge:
    def __init__(self, manifests_dir: Path, filename: str = "knowledge-documents.json"):
        self._path = manifests_dir / filename
        self._manifests_dir = manifests_dir
        self._field_names = {f.name for f in fields(KnowledgeDocument)}

    def _read(self) -> list[dict]:
        if not self._path.exists():
            return []
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, docs: list[dict]) -> None:
        self._manifests_dir.mkdir(parents=True, exist_ok=True)
        # Atomic write: tmp + replace
        fd, tmp = tempfile.mkstemp(
            prefix=self._path.name + ".",
            suffix=".tmp",
            dir=str(self._manifests_dir),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(docs, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self._path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def _to_doc(self, raw: dict) -> KnowledgeDocument:
        # Tolerant of legacy entries that carry extra fields like
        # `accession`, `form`, `filing_date` — drop unknown keys so the
        # dataclass init doesn't blow up.
        clean = {k: v for k, v in raw.items() if k in self._field_names}
        # `effective_date` is optional but bootstrap always sets it for
        # EDGAR/Pillar 3 — `filing_date` is the same thing for EDGAR.
        if "effective_date" not in clean and raw.get("filing_date"):
            clean["effective_date"] = raw["filing_date"]
        return KnowledgeDocument(**clean)

    # --- KnowledgeRepository surface ---

    def list_all(self) -> Iterator[KnowledgeDocument]:
        for raw in self._read():
            yield self._to_doc(raw)

    def get(self, doc_id: DocId) -> Optional[KnowledgeDocument]:
        for raw in self._read():
            if raw.get("doc_id") == doc_id:
                return self._to_doc(raw)
        return None

    def upsert(self, doc: KnowledgeDocument) -> None:
        docs = self._read()
        doc.updated_at = now_iso()
        payload = doc.to_dict()
        for i, raw in enumerate(docs):
            if raw.get("doc_id") == doc.doc_id:
                # Preserve any legacy fields the original record carries
                # (form, accession, primary_doc, etc.) — overlay our
                # dataclass fields on top.
                docs[i] = {**raw, **payload}
                break
        else:
            docs.append(payload)
        self._write(docs)

    def delete(self, doc_id: DocId) -> bool:
        docs = self._read()
        kept = [d for d in docs if d.get("doc_id") != doc_id]
        if len(kept) == len(docs):
            return False
        self._write(kept)
        return True

    def last_updated_at(self) -> Optional[str]:
        if not self._path.exists():
            return None
        latest: Optional[str] = None
        for raw in self._read():
            ts = raw.get("updated_at") or raw.get("ingested_at")
            if ts and (latest is None or ts > latest):
                latest = ts
        return latest
