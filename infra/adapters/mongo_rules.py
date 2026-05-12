"""Mongo-backed RuleRepository.

Mirrors `infra/adapters/mongo_taxonomy.py`. The collection lives at
`ddq.rules`, keyed by `_id = rule_id`. A composite index on
`(engine, status)` keeps the hot `get_active(engine)` query fast.

The optional `cut_version` method builds a Merkle root over active rules
and signs it with ed25519, writing the snapshot to
`s3://bny-ddq-rules-sealed/{engine}/v{N}/snapshot.json`. This is *not*
called from the live approve path — only from a bootstrap script — so
the production approve path stays S3-independent.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict
from typing import Any, Iterator, Optional

from core.domain.rules import Rule, RuleEngine, RuleStatus


DEFAULT_DB = "ddq"
DEFAULT_COLLECTION = "rules"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _to_doc(rule: Rule) -> dict:
    d = asdict(rule)
    d["_id"] = rule.rule_id
    return d


def _from_doc(doc: dict) -> Rule:
    raw = {k: v for k, v in doc.items() if k != "_id"}
    return Rule.from_dict(raw)


class MongoRules:
    def __init__(self, mongo_client: Any, *, db: str = DEFAULT_DB, collection: str = DEFAULT_COLLECTION):
        self._mongo = mongo_client
        self._db = mongo_client[db]
        self._coll = self._db[collection]
        # Indexes — idempotent.
        self._coll.create_index([("engine", 1), ("status", 1)])
        self._coll.create_index("priority")
        self._coll.create_index("rule_id", unique=True)

    # --- RuleRepository surface ---

    def list_all(
        self,
        *,
        engine: Optional[RuleEngine] = None,
        status: Optional[RuleStatus] = None,
    ) -> Iterator[Rule]:
        query: dict = {}
        if engine:
            query["engine"] = engine
        if status:
            query["status"] = status
        for doc in self._coll.find(query, sort=[("priority", 1), ("rule_id", 1)]):
            yield _from_doc(doc)

    def get(self, rule_id: str) -> Optional[Rule]:
        doc = self._coll.find_one({"_id": rule_id})
        return _from_doc(doc) if doc else None

    def get_active(self, engine: RuleEngine) -> list[Rule]:
        return list(self.list_all(engine=engine, status="active"))

    def upsert(self, rule: Rule) -> None:
        existing = self.get(rule.rule_id)
        if existing is not None:
            rule.created_at = existing.created_at or rule.created_at
        if not rule.created_at:
            rule.created_at = _now_iso()
        rule.updated_at = _now_iso()
        self._coll.replace_one({"_id": rule.rule_id}, _to_doc(rule), upsert=True)

    def delete(self, rule_id: str, *, force: bool = False) -> bool:
        existing = self.get(rule_id)
        if existing is None:
            return False
        if "bootstrap" in existing.tags and not force:
            raise PermissionError(
                f"rule {rule_id} is bootstrap-tagged; pass force=True to delete"
            )
        result = self._coll.delete_one({"_id": rule_id})
        return result.deleted_count > 0

    def last_updated_at(self) -> Optional[str]:
        doc = self._coll.find_one(
            {},
            sort=[("updated_at", -1)],
            projection={"updated_at": 1},
        )
        return (doc or {}).get("updated_at")

    # --- optional sealed-snapshot helper (see module docstring) ---

    def snapshot(self, engine: RuleEngine) -> dict:
        """Build an unsigned snapshot of active rules. The caller is
        responsible for signing + writing to S3 — keeping this method
        side-effect-free lets tests exercise it without LocalStack."""
        from core.domain.taxonomy import merkle_root  # local import — avoids circular if domain grows

        active = self.get_active(engine)
        payload_hashes: list[str] = []
        import hashlib
        for r in active:
            body = json.dumps(r.to_dict(), sort_keys=True, separators=(",", ":"))
            payload_hashes.append("sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest())
        return {
            "engine": engine,
            "snapshot_at": _now_iso(),
            "rules": [r.to_dict() for r in active],
            "rule_count": len(active),
            "merkle_root": merkle_root(payload_hashes) if payload_hashes else "sha256:" + "0" * 64,
        }
