"""Filesystem-backed RuleRepository.

Storage layout:

  $manifests/rules/<rule_id>.json   — one file per rule

One-file-per-entry keeps writes O(1) and makes inspection in `git diff`
legible. Mirrors `infra/adapters/fs_canonical.py`.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Iterator, Optional

from core.domain.rules import Rule, RuleEngine, RuleStatus


_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class FsRules:
    def __init__(self, manifests_dir: Path):
        self._dir = Path(manifests_dir) / "rules"

    def _path(self, rule_id: str) -> Path:
        if not _ID_RE.match(rule_id):
            raise ValueError(
                f"invalid rule_id (must match {_ID_RE.pattern}): {rule_id!r}"
            )
        return self._dir / f"{rule_id}.json"

    # --- RuleRepository surface ---

    def list_all(
        self,
        *,
        engine: Optional[RuleEngine] = None,
        status: Optional[RuleStatus] = None,
    ) -> Iterator[Rule]:
        if not self._dir.exists():
            return
        for p in sorted(self._dir.glob("*.json")):
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            r = Rule.from_dict(raw)
            if engine is not None and r.engine != engine:
                continue
            if status is not None and r.status != status:
                continue
            yield r

    def get(self, rule_id: str) -> Optional[Rule]:
        path = self._path(rule_id)
        if not path.exists():
            return None
        return Rule.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def get_active(self, engine: RuleEngine) -> list[Rule]:
        return sorted(
            self.list_all(engine=engine, status="active"),
            key=lambda r: (r.priority, r.rule_id),
        )

    def upsert(self, rule: Rule) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        existing = self.get(rule.rule_id)
        if existing is not None:
            rule.created_at = existing.created_at or rule.created_at
        if not rule.created_at:
            rule.created_at = _now_iso()
        rule.updated_at = _now_iso()
        path = self._path(rule.rule_id)
        body = json.dumps(rule.to_dict(), indent=2, ensure_ascii=False, sort_keys=False)
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

    def delete(self, rule_id: str, *, force: bool = False) -> bool:
        existing = self.get(rule_id)
        if existing is None:
            return False
        if "bootstrap" in existing.tags and not force:
            raise PermissionError(
                f"rule {rule_id} is bootstrap-tagged; pass force=True to delete"
            )
        self._path(rule_id).unlink()
        return True

    def last_updated_at(self) -> Optional[str]:
        if not self._dir.exists():
            return None
        latest: Optional[str] = None
        for r in self.list_all():
            if r.updated_at and (latest is None or r.updated_at > latest):
                latest = r.updated_at
        return latest
