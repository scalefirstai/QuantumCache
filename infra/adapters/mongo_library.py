"""
Mongo-backed LibraryService adapter.

Live entries → MongoDB `library.entries`.
Sealed snapshots → S3 (Object Lock) at `s3://bny-ddq-library-sealed/<version>/`.

Per ddq.md §L04 invariant: any historical sealed response can be regenerated
with the exact library entry version it cited.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict
from typing import Iterator, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from pymongo import MongoClient
from pymongo.collection import Collection

from core.domain.library import (
    Approver,
    EntryId,
    EvidenceRef,
    LibraryEntry,
    LibraryKey,
    LibrarySnapshot,
    ProposalId,
)
from core.domain.taxonomy import merkle_root


SNAPSHOT_BUCKET = "bny-ddq-library-sealed"


def _to_doc(e: LibraryEntry) -> dict:
    d = e.to_canonical_dict()
    d["_id"] = e.entry_id
    d["created_at"] = e.created_at
    d["updated_at"] = e.updated_at
    return d


def _from_doc(doc: dict) -> LibraryEntry:
    return LibraryEntry(
        entry_id=doc["entry_id"],
        canonical_id=doc["canonical_id"],
        entity=doc["entity"],
        product=doc.get("product"),
        answer_text=doc["answer_text"],
        evidence_refs=[EvidenceRef(**e) for e in doc.get("evidence_refs", [])],
        approvers=[Approver(**a) for a in doc.get("approvers", [])],
        effective_date=doc.get("effective_date", ""),
        expiry_date=doc.get("expiry_date"),
        review_due=doc.get("review_due"),
        version=doc.get("version", 1),
        supersedes=doc.get("supersedes"),
        tags=doc.get("tags", ["bootstrap"]),
        do_not_answer=doc.get("do_not_answer", False),
        created_at=doc.get("created_at", dt.datetime.now(dt.timezone.utc).isoformat()),
        updated_at=doc.get("updated_at", dt.datetime.now(dt.timezone.utc).isoformat()),
    )


class MongoLibrary:
    """Implements `core.ports.library.LibraryService` (Day 9 surface)."""

    def __init__(self, mongo: MongoClient, s3, db_name: str = "ddq", coll_name: str = "library.entries"):
        self.mongo = mongo
        self.s3 = s3
        self.coll: Collection = mongo[db_name][coll_name]
        self.coll.create_index([("canonical_id", 1), ("entity", 1), ("product", 1)])

    # --- Day 9 surface ---

    def upsert(self, entry: LibraryEntry) -> None:
        self.coll.replace_one({"_id": entry.entry_id}, _to_doc(entry), upsert=True)

    def lookup(self, key: LibraryKey) -> Optional[LibraryEntry]:
        """Return highest-versioned non-expired entry for the key, falling back
        through (entity, null product), per ddq.md §L04 behavior.
        """
        for query in (
            {"canonical_id": key.canonical_id, "entity": key.entity, "product": key.product},
            {"canonical_id": key.canonical_id, "entity": key.entity, "product": None},
        ):
            doc = self.coll.find_one(query, sort=[("version", -1)])
            if doc:
                return _from_doc(doc)
        return None

    def list_all(self, version: Optional[str] = None) -> Iterator[LibraryEntry]:
        if version is None:
            for doc in self.coll.find({}, sort=[("entry_id", 1)]):
                yield _from_doc(doc)
            return
        snap = self.load_snapshot(version)
        for entry in snap.entries:
            yield _from_doc({**entry,
                             "created_at": snap.cut_at, "updated_at": snap.cut_at})

    def search(self, q: dict) -> list[LibraryEntry]:
        return [_from_doc(d) for d in self.coll.find(q)]

    def cut_version(
        self, version: str, signer_id: str, signer_priv_key_pem: bytes
    ) -> LibrarySnapshot:
        entries_live = sorted(self.list_all(version=None), key=lambda e: e.entry_id)
        entries = [e.to_canonical_dict() for e in entries_live]
        hashes = [e.content_hash() for e in entries_live]
        root = merkle_root(hashes)

        by_entity: dict[str, int] = {}
        for e in entries_live:
            by_entity[e.entity] = by_entity.get(e.entity, 0) + 1

        priv = serialization.load_pem_private_key(signer_priv_key_pem, password=None)
        if not isinstance(priv, Ed25519PrivateKey):
            raise ValueError("expected an Ed25519 private key")
        signature = priv.sign(root.encode("utf-8")).hex()

        snap = LibrarySnapshot(
            version=version,
            cut_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            entry_count=len(entries),
            by_entity=by_entity,
            merkle_root=root,
            signed_by=signer_id,
            signature=f"ed25519:{signature}",
            entries=entries,
        )

        body = json.dumps(asdict(snap), indent=2, sort_keys=False).encode("utf-8")
        self.s3.put_object(
            Bucket=SNAPSHOT_BUCKET, Key=f"{version}/snapshot.json",
            Body=body, ContentType="application/json",
            Metadata={"version": version, "merkle_root": root, "signed_by": signer_id},
        )
        pub_pem = priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.s3.put_object(
            Bucket=SNAPSHOT_BUCKET, Key=f"{version}/signing_key.pub.pem",
            Body=pub_pem, ContentType="application/x-pem-file",
        )
        return snap

    def load_snapshot(self, version: str) -> LibrarySnapshot:
        obj = self.s3.get_object(Bucket=SNAPSHOT_BUCKET, Key=f"{version}/snapshot.json")
        d = json.loads(obj["Body"].read())
        return LibrarySnapshot(**d)

    # --- M1 stubs ---
    def propose(self, draft: LibraryEntry, run_id: str) -> ProposalId:
        raise NotImplementedError("propose — M1 work (proposal queue + Temporal)")

    def approve(self, proposal_id: ProposalId, approver: Approver) -> LibraryEntry:
        raise NotImplementedError("approve — M1 work (approval workflow)")

    def expire(self, entry_id: EntryId, reason: str) -> None:
        self.coll.update_one(
            {"_id": entry_id},
            {"$set": {"expiry_date": dt.date.today().isoformat(),
                      "tags": {"$addToSet": "expired"},
                      "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()}},
        )
