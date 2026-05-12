"""
KnowledgeRepository Protocol — CRUD for the knowledge corpus manifest.

The bytes are content-addressed and live in S3 (Object Lock for sealed
sources); this port owns the *metadata* layer only. Bytes ingestion
stays in `data/bootstrap/`.
"""

from __future__ import annotations

from typing import Iterator, Optional, Protocol

from core.domain.knowledge import DocId, KnowledgeDocument


class KnowledgeRepository(Protocol):
    def list_all(self) -> Iterator[KnowledgeDocument]: ...
    def get(self, doc_id: DocId) -> Optional[KnowledgeDocument]: ...
    def upsert(self, doc: KnowledgeDocument) -> None: ...
    def delete(self, doc_id: DocId) -> bool: ...
    def last_updated_at(self) -> Optional[str]: ...
