"""
AuditDatasetRepository Protocol — read + verify + append-redact wrapper
over the sealed-run journals.

Wraps `core.ports.sealed_runs.SealedRunsRepository` (which is itself the
read side of L01) with two extra operations:

  - `verify(run_id)` — re-runs the chain-integrity + Merkle-root checks
    that the orchestrator's post-hoc verifier performs on every sealed
    run. Read-only.

  - `add_redaction(run_id, redaction)` / `list_redactions(run_id)` —
    append a redaction record to a side log. Sealed-run JSON is never
    rewritten (ddq.md invariant 2).
"""

from __future__ import annotations

from typing import Iterator, Optional, Protocol

from core.domain.audit_redaction import AuditRedaction


class AuditDatasetRepository(Protocol):
    def list_runs(self) -> Iterator[dict]: ...
    def get_run(self, run_id: str) -> Optional[dict]: ...
    def verify(self, run_id: str) -> dict: ...
    def add_redaction(self, redaction: AuditRedaction) -> AuditRedaction: ...
    def list_redactions(self, run_id: str) -> list[AuditRedaction]: ...
    def last_updated_at(self) -> Optional[str]: ...
