"""
Filesystem-backed CanonicalRepository.

Storage layout:

  $manifests/canonical/<canonical_id>.json   — one file per entry
                                                (CanonicalQuestion.to_canonical_dict()
                                                + timestamps)

One-file-per-entry keeps writes O(1) regardless of taxonomy size and
makes inspection in `git diff` legible.

The fs adapter does NOT touch Qdrant / Mongo / S3 — it is a standalone
read-write store. Production wiring routes through `MongoTaxonomy`
(the existing adapter).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Iterator, Optional

from core.domain.taxonomy import (
    CanonicalId,
    CanonicalQuestion,
    FrameworkMapping,
)


_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class FsCanonical:
    def __init__(self, manifests_dir: Path):
        self._dir = manifests_dir / "canonical"

    def _path(self, canonical_id: CanonicalId) -> Path:
        if not _ID_RE.match(canonical_id):
            raise ValueError(
                f"invalid canonical_id (must match {_ID_RE.pattern}): {canonical_id!r}"
            )
        return self._dir / f"{canonical_id}.json"

    @staticmethod
    def _to_question(raw: dict) -> CanonicalQuestion:
        return CanonicalQuestion(
            canonical_id=raw["canonical_id"],
            label=raw.get("label", ""),
            description=raw.get("description", ""),
            parent_id=raw.get("parent_id"),
            framework_mappings=[
                FrameworkMapping(**m) for m in raw.get("framework_mappings", [])
            ],
            synonyms_embedding=raw.get("synonyms_embedding"),
            tier=int(raw.get("tier", 2)),
            do_not_answer=bool(raw.get("do_not_answer", False)),
            owners=list(raw.get("owners", [])),
            tags=list(raw.get("tags", [])),
            created_at=raw.get("created_at", _now_iso()),
            updated_at=raw.get("updated_at", _now_iso()),
        )

    @staticmethod
    def _from_question(q: CanonicalQuestion) -> dict:
        d = q.to_canonical_dict()
        d["created_at"] = q.created_at
        d["updated_at"] = q.updated_at
        d["synonyms_embedding"] = q.synonyms_embedding
        return d

    # --- CanonicalRepository surface ---

    def list_all(self) -> Iterator[CanonicalQuestion]:
        if not self._dir.exists():
            return
        for p in sorted(self._dir.glob("*.json")):
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            yield self._to_question(raw)

    def get(self, canonical_id: CanonicalId) -> Optional[CanonicalQuestion]:
        path = self._path(canonical_id)
        if not path.exists():
            return None
        return self._to_question(json.loads(path.read_text(encoding="utf-8")))

    def upsert(self, q: CanonicalQuestion) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        existing = self.get(q.canonical_id)
        if existing is not None:
            # Preserve created_at on update.
            q.created_at = existing.created_at
        q.updated_at = _now_iso()
        path = self._path(q.canonical_id)
        body = json.dumps(self._from_question(q), indent=2, ensure_ascii=False)
        fd, tmp = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=str(self._dir),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def delete(self, canonical_id: CanonicalId, *, force: bool = False) -> bool:
        existing = self.get(canonical_id)
        if existing is None:
            return False
        if "bootstrap" in existing.tags and not force:
            raise PermissionError(
                f"canonical {canonical_id} is bootstrap-tagged; pass force=True"
            )
        self._path(canonical_id).unlink()
        return True

    def last_updated_at(self) -> Optional[str]:
        if not self._dir.exists():
            return None
        latest: Optional[str] = None
        for q in self.list_all():
            if q.updated_at and (latest is None or q.updated_at > latest):
                latest = q.updated_at
        return latest
