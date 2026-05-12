"""
Filesystem-backed AuditDatasetRepository.

Wraps an existing `SealedRunsRepository` (`FsSealedRuns` or
`S3SealedRuns`) for read+verify, and stores redactions as side files:

  $manifests/audit-redactions/<run_id>.json    — list of AuditRedaction dicts

Sealed runs themselves are never rewritten — ddq.md invariant 2.

The integrity verifier matches the post-hoc check in
`data/bootstrap/11_wire_up.py`:

  1. For each event, recompute payload_hash + chain_hash and compare.
  2. Recompute the Merkle root over all payload_hashes (sorted lex) and
     compare to the sealed `merkle_root` field.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Iterator, Optional

from core.domain.audit_redaction import AuditRedaction, now_iso
from core.domain.taxonomy import merkle_root


ZERO_HASH = "sha256:" + "0" * 64


def _sha256_hex(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _payload_hash(payload: dict) -> str:
    return _sha256_hex(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _chain_hash(prev_hash: str, event_id: str, payload_hash: str) -> str:
    # Order matches `chain_events()` in apps/orchestrator/main.py and
    # data/bootstrap/11_wire_up.py: prev + event_id + payload_hash.
    return _sha256_hex((prev_hash + event_id + payload_hash).encode("utf-8"))


class FsAuditDataset:
    def __init__(self, sealed_runs, manifests_dir: Path):
        self._runs = sealed_runs
        self._redactions_dir = manifests_dir / "audit-redactions"

    # --- read surface ---

    def list_runs(self) -> Iterator[dict]:
        for run_id in self._runs.list_run_ids():
            sealed = self._runs.get_sealed_run(run_id)
            if sealed is None:
                continue
            yield sealed

    def get_run(self, run_id: str) -> Optional[dict]:
        return self._runs.get_sealed_run(run_id)

    # --- verify ---

    def verify(self, run_id: str) -> dict:
        sealed = self._runs.get_sealed_run(run_id)
        if sealed is None:
            raise FileNotFoundError(f"run not found: {run_id}")
        events = sealed.get("events", [])
        chain_ok = True
        broken_at: Optional[str] = None
        prev = ZERO_HASH
        recomputed_payload_hashes: list[str] = []
        for ev in events:
            ph = _payload_hash(ev["payload"])
            ch = _chain_hash(prev, ev["event_id"], ph)
            recomputed_payload_hashes.append(ph)
            if ev.get("payload_hash") != ph or ev.get("chain_hash") != ch \
                    or ev.get("prev_hash") != prev:
                chain_ok = False
                broken_at = ev["event_id"]
                break
            prev = ch
        # Merkle root is computed over content_hashes sorted lex (same as
        # core.domain.taxonomy.merkle_root) — orchestrator writes that
        # form into `merkle_root` on the run.
        recomputed_merkle = merkle_root(recomputed_payload_hashes)
        expected_merkle = sealed.get("merkle_root")
        merkle_ok = (expected_merkle == recomputed_merkle) if expected_merkle else None
        return {
            "chainOk": chain_ok,
            "merkleOk": merkle_ok if merkle_ok is not None else chain_ok,
            "expectedMerkle": expected_merkle,
            "recomputedMerkle": recomputed_merkle,
            "brokenAt": broken_at,
            "verifiedAt": now_iso(),
        }

    # --- redactions (append-only side log) ---

    def _redact_path(self, run_id: str) -> Path:
        return self._redactions_dir / f"{run_id}.json"

    def _read_redactions(self, run_id: str) -> list[dict]:
        path = self._redact_path(run_id)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_redactions(self, run_id: str, items: list[dict]) -> None:
        self._redactions_dir.mkdir(parents=True, exist_ok=True)
        path = self._redact_path(run_id)
        fd, tmp = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=str(self._redactions_dir),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2)
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def add_redaction(self, redaction: AuditRedaction) -> AuditRedaction:
        if self._runs.get_sealed_run(redaction.run_id) is None:
            raise FileNotFoundError(f"run not found: {redaction.run_id}")
        if not redaction.redaction_id:
            redaction.redaction_id = "red_" + secrets.token_hex(6)
        if not redaction.ts:
            redaction.ts = now_iso()
        items = self._read_redactions(redaction.run_id)
        items.append(redaction.to_dict())
        self._write_redactions(redaction.run_id, items)
        return redaction

    def list_redactions(self, run_id: str) -> list[AuditRedaction]:
        return [AuditRedaction(**raw) for raw in self._read_redactions(run_id)]

    def last_updated_at(self) -> Optional[str]:
        latest: Optional[str] = None
        for run_id in self._runs.list_run_ids():
            sealed = self._runs.get_sealed_run(run_id)
            if sealed:
                ts = sealed.get("sealed_at")
                if ts and (latest is None or ts > latest):
                    latest = ts
        return latest
