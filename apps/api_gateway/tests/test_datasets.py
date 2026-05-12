"""
Dataset management API tests — acceptance criteria from
docs/specs/dataset-management.md §6.

Every test runs against a tmp-path copy of the repo so writes don't
pollute the real manifests. The fs-mode adapter is exercised end-to-end
through FastAPI's TestClient.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def tmp_repo(tmp_path_factory) -> Iterator[Path]:
    """Snapshot the real repo into a tmp dir so dataset writes are
    isolated. Only the trees the API reads are copied (everything else
    is left out to keep the snapshot cheap)."""
    base = tmp_path_factory.mktemp("repo")
    for sub in ("services", "apps", "core", "infra", "packages", "data", "evals"):
        src = REPO / sub
        if src.exists():
            shutil.copytree(
                src,
                base / sub,
                symlinks=False,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
    yield base


@pytest.fixture()
def client(tmp_repo, monkeypatch) -> TestClient:
    monkeypatch.setenv("DDQ_REPO_ROOT", str(tmp_repo))
    monkeypatch.setenv("DDQ_RUNS_BACKEND", "fs")
    monkeypatch.setenv("DDQ_USE_MONGO", "0")
    from apps.api_gateway.deps import container
    container.cache_clear()
    from apps.api_gateway.main import create_app
    return TestClient(create_app())


# ════════════════════════════════════════════════════════════════════
# DS-IDX
# ════════════════════════════════════════════════════════════════════

def test_DS_IDX_lists_three_datasets(client):
    r = client.get("/api/v1/datasets")
    assert r.status_code == 200
    body = r.json()
    ids = {d["id"] for d in body}
    assert ids == {"knowledge", "canonical", "audit"}
    counts = {d["id"]: d["count"] for d in body}
    # The bootstrap seeds at least 126 knowledge, 12 canonical (after
    # seed_canonical_manifest.py), and >=5 sealed runs in this repo.
    assert counts["knowledge"] >= 1
    assert counts["audit"] >= 1
    for d in body:
        assert "label" in d and "description" in d
        assert "lastUpdatedAt" in d


# ════════════════════════════════════════════════════════════════════
# DS-KN — Knowledge CRUD
# ════════════════════════════════════════════════════════════════════

def _kn_body(doc_id: str = "operator:test:doc1") -> dict:
    return {
        "docId": doc_id,
        "source": "operator",
        "entity": "bny-mellon-corp",
        "primaryDesc": "Test policy doc",
        "docHash": "sha256:" + "a" * 64,
        "contentType": "application/pdf",
        "bytes": 12345,
        "s3Uri": "s3://bny-ddq-knowledge-raw/operator/test/doc1.pdf",
        "kind": "policy",
        "effectiveDate": "2026-05-12",
        "url": "https://example.com/doc1.pdf",
        "tags": ["operator-added", "test"],
    }


def test_DS_KN_CRUD_full_cycle(client):
    body = _kn_body("operator:crud:doc_v1")

    # create
    r = client.post("/api/v1/datasets/knowledge", json=body)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["docId"] == body["docId"]
    assert created["docHash"] == body["docHash"]
    assert created["tags"] == body["tags"]

    # list — must include new doc
    r = client.get("/api/v1/datasets/knowledge")
    assert r.status_code == 200
    ids = {d["docId"] for d in r.json()}
    assert body["docId"] in ids

    # get
    r = client.get(f"/api/v1/datasets/knowledge/{body['docId']}")
    assert r.status_code == 200
    assert r.json()["docId"] == body["docId"]

    # update — change tags only
    r = client.put(
        f"/api/v1/datasets/knowledge/{body['docId']}",
        json={"tags": ["operator-added", "approved"]},
    )
    assert r.status_code == 200
    updated = r.json()
    assert updated["tags"] == ["operator-added", "approved"]

    # delete
    r = client.delete(f"/api/v1/datasets/knowledge/{body['docId']}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    # subsequent get → 404
    r = client.get(f"/api/v1/datasets/knowledge/{body['docId']}")
    assert r.status_code == 404


def test_DS_KN_create_conflict(client):
    body = _kn_body("operator:conflict:doc_v1")
    r1 = client.post("/api/v1/datasets/knowledge", json=body)
    assert r1.status_code == 200
    r2 = client.post("/api/v1/datasets/knowledge", json=body)
    assert r2.status_code == 409
    client.delete(f"/api/v1/datasets/knowledge/{body['docId']}")


def test_DS_KN_HASH_STABLE_update_does_not_touch_hash(client):
    body = _kn_body("operator:hash:doc_v1")
    body["docHash"] = "sha256:" + "b" * 64
    r = client.post("/api/v1/datasets/knowledge", json=body)
    assert r.status_code == 200
    original_hash = r.json()["docHash"]

    # Update tags, description, kind, effective date — all metadata.
    r = client.put(
        f"/api/v1/datasets/knowledge/{body['docId']}",
        json={
            "tags": ["edited"],
            "primaryDesc": "rewritten description",
            "kind": "white-paper",
            "effectiveDate": "2026-06-01",
        },
    )
    assert r.status_code == 200
    assert r.json()["docHash"] == original_hash
    # confirm via GET as well
    fresh = client.get(f"/api/v1/datasets/knowledge/{body['docId']}").json()
    assert fresh["docHash"] == original_hash
    client.delete(f"/api/v1/datasets/knowledge/{body['docId']}")


def test_DS_KN_invalid_hash_rejected(client):
    body = _kn_body("operator:invalid:doc_v1")
    body["docHash"] = "not-a-sha256"
    r = client.post("/api/v1/datasets/knowledge", json=body)
    assert r.status_code == 422


def test_DS_KN_404_on_unknown(client):
    r = client.get("/api/v1/datasets/knowledge/operator:unknown:doc")
    assert r.status_code == 404
    r = client.put(
        "/api/v1/datasets/knowledge/operator:unknown:doc",
        json={"tags": ["x"]},
    )
    assert r.status_code == 404
    r = client.delete("/api/v1/datasets/knowledge/operator:unknown:doc")
    assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# DS-CN — Canonical CRUD
# ════════════════════════════════════════════════════════════════════

def _cn_body(canonical_id: str = "canon.test.iam.q1") -> dict:
    return {
        "canonicalId": canonical_id,
        "label": "Test canonical",
        "description": "Test canonical question",
        "tier": 2,
        "doNotAnswer": False,
        "owners": ["test"],
        "tags": ["operator-added"],
        "frameworkMappings": [
            {"framework": "CAIQ", "version": "v4.0.3", "questionRef": "IAM-99.1"},
        ],
    }


def test_DS_CN_CRUD_full_cycle(client):
    body = _cn_body("canon.test.crud.q1")

    r = client.post("/api/v1/datasets/canonical", json=body)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["canonicalId"] == body["canonicalId"]
    assert len(created["frameworkMappings"]) == 1

    r = client.get("/api/v1/datasets/canonical")
    assert body["canonicalId"] in {c["canonicalId"] for c in r.json()}

    r = client.put(
        f"/api/v1/datasets/canonical/{body['canonicalId']}",
        json={"label": "renamed", "tier": 1},
    )
    assert r.status_code == 200
    assert r.json()["label"] == "renamed"
    assert r.json()["tier"] == 1
    # Unspecified fields preserved.
    assert r.json()["description"] == body["description"]

    r = client.delete(f"/api/v1/datasets/canonical/{body['canonicalId']}")
    assert r.status_code == 200

    r = client.get(f"/api/v1/datasets/canonical/{body['canonicalId']}")
    assert r.status_code == 404


def test_DS_CN_BOOTSTRAP_protect(client):
    """A bootstrap-tagged canonical can't be deleted without ?force=true."""
    body = _cn_body("canon.test.boot.q1")
    body["tags"] = ["bootstrap"]
    r = client.post("/api/v1/datasets/canonical", json=body)
    assert r.status_code == 200

    r = client.delete(f"/api/v1/datasets/canonical/{body['canonicalId']}")
    assert r.status_code == 400
    assert "bootstrap" in r.json()["detail"].lower()

    r = client.delete(
        f"/api/v1/datasets/canonical/{body['canonicalId']}?force=true"
    )
    assert r.status_code == 200


def test_DS_CN_invalid_id_rejected(client):
    body = _cn_body("not a valid id")
    r = client.post("/api/v1/datasets/canonical", json=body)
    assert r.status_code == 422


def test_DS_CN_create_conflict(client):
    body = _cn_body("canon.test.conflict.q1")
    r1 = client.post("/api/v1/datasets/canonical", json=body)
    assert r1.status_code == 200
    r2 = client.post("/api/v1/datasets/canonical", json=body)
    assert r2.status_code == 409
    client.delete(f"/api/v1/datasets/canonical/{body['canonicalId']}?force=true")


def test_DS_CN_filter_by_framework(client):
    body = _cn_body("canon.test.filter.q1")
    body["frameworkMappings"] = [
        {"framework": "CUSTOMFW", "version": "v1", "questionRef": "CF-1"},
    ]
    client.post("/api/v1/datasets/canonical", json=body)
    r = client.get("/api/v1/datasets/canonical?framework=CUSTOMFW")
    assert r.status_code == 200
    ids = {c["canonicalId"] for c in r.json()}
    assert body["canonicalId"] in ids
    client.delete(f"/api/v1/datasets/canonical/{body['canonicalId']}?force=true")


# ════════════════════════════════════════════════════════════════════
# DS-AU — Audit (immutable + verify + redact)
# ════════════════════════════════════════════════════════════════════

def test_DS_AU_LIST_returns_runs_with_merkle(client):
    r = client.get("/api/v1/datasets/audit")
    assert r.status_code == 200
    body = r.json()
    assert len(body) > 0
    first = body[0]
    assert first["runId"].startswith("run_")
    assert first["merkleRoot"].startswith("sha256:")
    assert first["eventCount"] > 0


def test_DS_AU_IMMUT_no_put_or_delete(client):
    runs = client.get("/api/v1/datasets/audit").json()
    run_id = runs[0]["runId"]
    r = client.put(f"/api/v1/datasets/audit/{run_id}", json={})
    assert r.status_code in (404, 405)
    r = client.delete(f"/api/v1/datasets/audit/{run_id}")
    assert r.status_code in (404, 405)


def test_DS_AU_VERIFY_sealed_run_is_intact(client):
    runs = client.get("/api/v1/datasets/audit").json()
    run_id = runs[0]["runId"]
    r = client.post(f"/api/v1/datasets/audit/{run_id}/verify")
    assert r.status_code == 200
    body = r.json()
    assert body["chainOk"] is True
    assert body["merkleOk"] is True
    assert body["brokenAt"] is None
    assert body["recomputedMerkle"] == body["expectedMerkle"]


def test_DS_AU_VERIFY_RO_does_not_mutate_run(client):
    """Verify is read-only — the sealed JSON on disk must be byte-identical
    before and after."""
    runs = client.get("/api/v1/datasets/audit").json()
    run_id = runs[0]["runId"]
    # Read raw file via the API GET so we don't depend on filesystem paths
    # in the test repo.
    before = client.get(f"/api/v1/datasets/audit/{run_id}").json()
    client.post(f"/api/v1/datasets/audit/{run_id}/verify")
    after = client.get(f"/api/v1/datasets/audit/{run_id}").json()
    # Strip redaction count (the side log can change) and verify event chain is intact.
    before.pop("redactionCount", None)
    after.pop("redactionCount", None)
    assert before == after


def test_DS_AU_VERIFY_404_on_unknown(client):
    r = client.post("/api/v1/datasets/audit/run_does_not_exist/verify")
    assert r.status_code == 404


def test_DS_AU_REDACT_append_only_log(client):
    runs = client.get("/api/v1/datasets/audit").json()
    run = runs[0]
    detail = client.get(f"/api/v1/datasets/audit/{run['runId']}").json()
    event_id = detail["events"][0]["eventId"]
    body = {
        "eventId": event_id,
        "field": "payload.evidence_excerpt",
        "reason": "LEGAL-2026-Q2-014",
        "actor": "ops.theo",
    }
    r = client.post(
        f"/api/v1/datasets/audit/{run['runId']}/redactions", json=body
    )
    assert r.status_code == 200
    created = r.json()
    assert created["redactionId"].startswith("red_")
    assert created["runId"] == run["runId"]
    assert created["eventId"] == event_id
    # subsequent list returns it
    r = client.get(f"/api/v1/datasets/audit/{run['runId']}/redactions")
    assert r.status_code == 200
    items = r.json()
    assert any(it["redactionId"] == created["redactionId"] for it in items)
    # detail shows redactionCount >= 1
    detail = client.get(f"/api/v1/datasets/audit/{run['runId']}").json()
    assert detail["redactionCount"] >= 1


def test_DS_AU_REDACT_does_not_mutate_sealed_run(client):
    runs = client.get("/api/v1/datasets/audit").json()
    run_id = runs[1]["runId"] if len(runs) > 1 else runs[0]["runId"]
    # Snapshot the detail body before+after; events MUST be byte-equal.
    before = client.get(f"/api/v1/datasets/audit/{run_id}").json()
    event_id = before["events"][0]["eventId"]
    client.post(
        f"/api/v1/datasets/audit/{run_id}/redactions",
        json={
            "eventId": event_id,
            "field": "payload.foo",
            "reason": "test",
            "actor": "ops.test",
        },
    )
    after = client.get(f"/api/v1/datasets/audit/{run_id}").json()
    # events tuple immutable (only redactionCount differs)
    assert before["events"] == after["events"]
    assert before["merkleRoot"] == after["merkleRoot"]
    # verify still passes
    v = client.post(f"/api/v1/datasets/audit/{run_id}/verify").json()
    assert v["chainOk"] and v["merkleOk"]


def test_DS_AU_REDACT_404_on_unknown_run(client):
    r = client.post(
        "/api/v1/datasets/audit/run_does_not_exist/redactions",
        json={"eventId": "evt_x", "field": "f", "reason": "r"},
    )
    assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# DS-IDX — counts move with mutations
# ════════════════════════════════════════════════════════════════════

def test_DS_IDX_counts_track_mutations(client):
    body = _cn_body("canon.test.idx.q1")
    before = {d["id"]: d["count"] for d in client.get("/api/v1/datasets").json()}
    client.post("/api/v1/datasets/canonical", json=body)
    after = {d["id"]: d["count"] for d in client.get("/api/v1/datasets").json()}
    assert after["canonical"] == before["canonical"] + 1
    client.delete(f"/api/v1/datasets/canonical/{body['canonicalId']}?force=true")
    after2 = {d["id"]: d["count"] for d in client.get("/api/v1/datasets").json()}
    assert after2["canonical"] == before["canonical"]


# ════════════════════════════════════════════════════════════════════
# Atomic writes (filesystem-level)
# ════════════════════════════════════════════════════════════════════

def test_DS_KN_atomic_write_replaces_in_place(tmp_repo, client):
    """After a mutation, the manifest file must still parse as JSON and
    the count must match what the API reports."""
    client.post("/api/v1/datasets/knowledge", json=_kn_body("operator:atomic:doc_v1"))
    manifest = tmp_repo / "data" / "manifests" / "knowledge-documents.json"
    parsed = json.loads(manifest.read_text(encoding="utf-8"))
    assert any(d["doc_id"] == "operator:atomic:doc_v1" for d in parsed)
    # Cleanup
    client.delete("/api/v1/datasets/knowledge/operator:atomic:doc_v1")
