"""
Mongo-backed TaxonomyService adapter.

Live entries → MongoDB `taxonomy.questions`.
Sealed snapshots → S3 (Object Lock) at `s3://bny-ddq-taxonomy-snapshots/<version>/`.

Per ddq.md §L05:
  - `cut_version` writes a signed snapshot containing every entry.
  - `get(..., version="tx_v0.1")` MUST recover bit-exact entries from S3.
"""

from __future__ import annotations

import datetime as dt
import io
import json
from dataclasses import asdict
from typing import Iterator, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from pymongo import MongoClient
from pymongo.collection import Collection

from core.domain.taxonomy import (
    CanonicalId,
    CanonicalQuestion,
    FrameworkMapping,
    TaxonomySnapshot,
    TaxonomyVersion,
    merkle_root,
)


SNAPSHOT_BUCKET = "bny-ddq-taxonomy-snapshots"


def _to_doc(q: CanonicalQuestion) -> dict:
    """CanonicalQuestion → Mongo doc. _id = canonical_id for direct lookup."""
    d = q.to_canonical_dict()
    d["_id"] = q.canonical_id
    d["synonyms_embedding"] = q.synonyms_embedding
    d["created_at"] = q.created_at
    d["updated_at"] = q.updated_at
    return d


def _from_doc(doc: dict) -> CanonicalQuestion:
    return CanonicalQuestion(
        canonical_id=doc["canonical_id"],
        label=doc["label"],
        description=doc["description"],
        parent_id=doc.get("parent_id"),
        framework_mappings=[FrameworkMapping(**m) for m in doc.get("framework_mappings", [])],
        synonyms_embedding=doc.get("synonyms_embedding"),
        tier=doc.get("tier", 2),
        do_not_answer=doc.get("do_not_answer", False),
        owners=doc.get("owners", ["bootstrap.seed"]),
        tags=doc.get("tags", ["bootstrap"]),
        created_at=doc.get("created_at", dt.datetime.now(dt.timezone.utc).isoformat()),
        updated_at=doc.get("updated_at", dt.datetime.now(dt.timezone.utc).isoformat()),
    )


class MongoTaxonomy:
    """
    Implements `core.ports.taxonomy.TaxonomyService` (Day 8 surface only).
    """

    def __init__(self, mongo: MongoClient, s3, db_name: str = "ddq", coll_name: str = "taxonomy.questions"):
        self.mongo = mongo
        self.s3 = s3
        self.coll: Collection = mongo[db_name][coll_name]
        self.coll.create_index("canonical_id", unique=True)

    # --- Day 8 surface ---

    def upsert(self, q: CanonicalQuestion) -> None:
        self.coll.replace_one({"_id": q.canonical_id}, _to_doc(q), upsert=True)

    def get(self, canonical_id: CanonicalId, version: Optional[TaxonomyVersion] = None) -> Optional[CanonicalQuestion]:
        if version is None:
            doc = self.coll.find_one({"_id": canonical_id})
            return _from_doc(doc) if doc else None
        # Versioned read: pull the snapshot, find by canonical_id.
        snap = self.load_snapshot(version)
        for entry in snap.questions:
            if entry["canonical_id"] == canonical_id:
                return _from_doc({**entry, "synonyms_embedding": None,
                                  "created_at": snap.cut_at, "updated_at": snap.cut_at})
        return None

    def list_all(self, version: Optional[TaxonomyVersion] = None) -> Iterator[CanonicalQuestion]:
        if version is None:
            for doc in self.coll.find({}, sort=[("canonical_id", 1)]):
                yield _from_doc(doc)
            return
        snap = self.load_snapshot(version)
        for entry in snap.questions:
            yield _from_doc({**entry, "synonyms_embedding": None,
                             "created_at": snap.cut_at, "updated_at": snap.cut_at})

    def cut_version(
        self, version: TaxonomyVersion, signer_id: str, signer_priv_key_pem: bytes
    ) -> TaxonomySnapshot:
        # Pull every entry deterministically.
        questions = list(self.list_all(version=None))
        ordered = sorted(questions, key=lambda q: q.canonical_id)
        entries = [q.to_canonical_dict() for q in ordered]
        hashes = [q.content_hash() for q in ordered]
        root = merkle_root(hashes)

        coverage: dict[str, int] = {}
        for q in ordered:
            for m in q.framework_mappings:
                coverage[m.framework] = coverage.get(m.framework, 0) + 1

        # Sign the merkle root with ed25519.
        priv = serialization.load_pem_private_key(signer_priv_key_pem, password=None)
        if not isinstance(priv, Ed25519PrivateKey):
            raise ValueError("expected an Ed25519 private key")
        signature = priv.sign(root.encode("utf-8")).hex()

        snap = TaxonomySnapshot(
            version=version,
            cut_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            question_count=len(entries),
            framework_coverage=coverage,
            merkle_root=root,
            signed_by=signer_id,
            signature=f"ed25519:{signature}",
            questions=entries,
        )

        # Seal to S3 (Object Lock bucket).
        self._put_snapshot(snap, priv.public_key())
        return snap

    def _put_snapshot(self, snap: TaxonomySnapshot, public_key: Ed25519PublicKey) -> None:
        body = json.dumps(asdict(snap), indent=2, sort_keys=False).encode("utf-8")
        key = f"{snap.version}/snapshot.json"
        self.s3.put_object(
            Bucket=SNAPSHOT_BUCKET, Key=key, Body=body,
            ContentType="application/json",
            Metadata={"version": snap.version, "merkle_root": snap.merkle_root,
                      "signed_by": snap.signed_by},
        )
        # Co-locate the public key for verification (no Object Lock needed on
        # pubkey since it's reproducible; included for auditor convenience).
        pub_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.s3.put_object(
            Bucket=SNAPSHOT_BUCKET, Key=f"{snap.version}/signing_key.pub.pem",
            Body=pub_pem, ContentType="application/x-pem-file",
        )

    def load_snapshot(self, version: TaxonomyVersion) -> TaxonomySnapshot:
        obj = self.s3.get_object(Bucket=SNAPSHOT_BUCKET, Key=f"{version}/snapshot.json")
        body = obj["Body"].read()
        d = json.loads(body)
        return TaxonomySnapshot(**d)

    # --- M1 stubs (Protocol compliance) ---
    def map_framework_question(self, framework: str, ref: str, version: str) -> Optional[CanonicalId]:
        # Linear scan — fine at ~500 entries; index later if it grows.
        for doc in self.coll.find({"framework_mappings.framework": framework,
                                   "framework_mappings.version": version,
                                   "framework_mappings.question_ref": ref}):
            return doc["canonical_id"]
        return None

    def classify_new_question(self, text: str, framework: str) -> dict:
        raise NotImplementedError("classify_new_question — M1 work (needs Qdrant lookup)")

    def propose_mapping(self, framework_question: dict, candidate: CanonicalId, run_id: str) -> str:
        raise NotImplementedError("propose_mapping — M1 work (needs proposal queue)")
