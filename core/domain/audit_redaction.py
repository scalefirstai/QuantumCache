"""
Audit redaction record — ddq.md §L01 invariant 2 ("no edits to sealed
records"). Redactions are *appended* to a side log; the sealed run JSON
on S3 is never rewritten. The UI uses these to display "this field was
redacted under legal hold" without breaking chain integrity.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass


@dataclass
class AuditRedaction:
    redaction_id: str       # "red_<hex>"
    run_id: str
    event_id: str           # the specific event being redacted
    field: str              # e.g., "payload.evidence_excerpt"
    reason: str             # legal-hold reference / SOC ticket id
    actor: str              # operator user_id
    ts: str                 # ISO8601 UTC

    def to_dict(self) -> dict:
        return asdict(self)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
