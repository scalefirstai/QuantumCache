"""
CanonicalRepository Protocol — CRUD-style accessor over canonical questions.

Wraps `core.ports.taxonomy.TaxonomyService`-style writes with explicit
delete semantics. The fs adapter is self-contained (no Mongo dependency)
so the API can run in dev without LocalStack; the mongo adapter delegates
to `MongoTaxonomy.upsert/list_all/get` and adds a soft-delete `tombstone`.
"""

from __future__ import annotations

from typing import Iterator, Optional, Protocol

from core.domain.taxonomy import CanonicalId, CanonicalQuestion


class CanonicalRepository(Protocol):
    def list_all(self) -> Iterator[CanonicalQuestion]: ...
    def get(self, canonical_id: CanonicalId) -> Optional[CanonicalQuestion]: ...
    def upsert(self, q: CanonicalQuestion) -> None: ...
    def delete(self, canonical_id: CanonicalId, *, force: bool = False) -> bool: ...
    def last_updated_at(self) -> Optional[str]: ...
