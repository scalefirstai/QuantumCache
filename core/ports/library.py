"""
LibraryService Protocol — ddq.md §L04.

Day 9 surface: upsert / lookup / search / cut_version / load_snapshot.
M1 surface (stubs): propose / approve / expire — full proposal workflow
needs Temporal + the SME UI.
"""

from __future__ import annotations

from typing import Iterator, Optional, Protocol

from core.domain.library import (
    Approver,
    EntryId,
    LibraryEntry,
    LibraryKey,
    LibrarySnapshot,
    ProposalId,
)


class LibraryService(Protocol):
    # --- Day 9 surface ---
    def upsert(self, entry: LibraryEntry) -> None: ...
    def lookup(self, key: LibraryKey) -> Optional[LibraryEntry]: ...
    def list_all(self, version: Optional[str] = None) -> Iterator[LibraryEntry]: ...
    def search(self, q: dict) -> list[LibraryEntry]: ...
    def cut_version(self, version: str, signer_id: str, signer_priv_key_pem: bytes) -> LibrarySnapshot: ...
    def load_snapshot(self, version: str) -> LibrarySnapshot: ...

    # --- M1 surface ---
    def propose(self, draft: LibraryEntry, run_id: str) -> ProposalId: ...
    def approve(self, proposal_id: ProposalId, approver: Approver) -> LibraryEntry: ...
    def expire(self, entry_id: EntryId, reason: str) -> None: ...
