"""
TaxonomyService Protocol — ddq.md §L05.

Most methods are M1 work; what Day 8 needs is `upsert`, `get`, and
`cut_version`. Other methods are Protocol-declared so adapters can stub
them now and fill in later without breaking callers.
"""

from __future__ import annotations

from typing import Iterator, Optional, Protocol

from core.domain.taxonomy import (
    CanonicalId,
    CanonicalQuestion,
    TaxonomySnapshot,
    TaxonomyVersion,
)


class TaxonomyService(Protocol):
    # --- Day 8 surface ---
    def upsert(self, q: CanonicalQuestion) -> None: ...
    def get(self, canonical_id: CanonicalId, version: Optional[TaxonomyVersion] = None) -> Optional[CanonicalQuestion]: ...
    def list_all(self, version: Optional[TaxonomyVersion] = None) -> Iterator[CanonicalQuestion]: ...
    def cut_version(self, version: TaxonomyVersion, signer_id: str, signer_priv_key_pem: bytes) -> TaxonomySnapshot: ...
    def load_snapshot(self, version: TaxonomyVersion) -> TaxonomySnapshot: ...

    # --- M1 surface (stubs allowed) ---
    def map_framework_question(self, framework: str, ref: str, version: str) -> Optional[CanonicalId]: ...
    def classify_new_question(self, text: str, framework: str) -> dict: ...
    def propose_mapping(self, framework_question: dict, candidate: CanonicalId, run_id: str) -> str: ...
