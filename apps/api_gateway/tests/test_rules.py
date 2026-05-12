"""
Rule engine API tests — acceptance criteria from
docs/specs/rule-engine.md.

Runs against a tmp-path copy of the repo, FS adapter, no Mongo. Each
test starts from the bootstrap-seeded rule set (11 rules) so the
fixtures are realistic.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def tmp_repo(tmp_path_factory) -> Iterator[Path]:
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
# Listing / filtering
# ════════════════════════════════════════════════════════════════════

def test_RU_LIST_returns_seeded_rules(client):
    r = client.get("/api/v1/rules")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) >= 11
    ids = {d["ruleId"] for d in body}
    assert "freshness.library.expired" in ids
    assert "approval.halt.pii" in ids
    assert "approval.auto.clean" in ids


def test_RU_LIST_filter_by_engine(client):
    r = client.get("/api/v1/rules?engine=freshness")
    assert r.status_code == 200
    body = r.json()
    assert all(d["engine"] == "freshness" for d in body)
    assert len(body) == 4


def test_RU_LIST_filter_by_status(client):
    r = client.get("/api/v1/rules?status=active")
    assert r.status_code == 200
    assert all(d["status"] == "active" for d in r.json())


def test_RU_GET_detail(client):
    r = client.get("/api/v1/rules/freshness.library.expired")
    assert r.status_code == 200
    body = r.json()
    assert body["ruleId"] == "freshness.library.expired"
    assert body["engine"] == "freshness"
    assert body["when"]  # non-empty condition
    assert body["then"]["stale"] is True


def test_RU_GET_unknown_returns_404(client):
    r = client.get("/api/v1/rules/no.such.rule")
    assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# Create / update / delete
# ════════════════════════════════════════════════════════════════════

def _create_body(rule_id: str = "test.freshness.demo", **overrides) -> dict:
    body = {
        "ruleId": rule_id,
        "engine": "freshness",
        "title": "Test demo rule",
        "description": "Created by automated test",
        "priority": 200,
        "when": {"field": "library_entry.tags", "op": "contains", "value": "needs_review"},
        "then": {"stale": True, "reason": "tagged needs_review"},
        "tags": ["test"],
    }
    body.update(overrides)
    return body


def test_RU_POST_creates_draft(client):
    r = client.post("/api/v1/rules", json=_create_body())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "draft"
    assert body["version"] == "1.0.0"
    assert body["reviewQueue"] == "ops"  # freshness default
    # Cleanup
    client.delete(f"/api/v1/rules/{body['ruleId']}")


def test_RU_POST_duplicate_returns_409(client):
    body = _create_body("test.duplicate")
    r1 = client.post("/api/v1/rules", json=body)
    assert r1.status_code == 200
    r2 = client.post("/api/v1/rules", json=body)
    assert r2.status_code == 409
    client.delete(f"/api/v1/rules/{body['ruleId']}")


def test_RU_POST_invalid_dsl_returns_422(client):
    body = _create_body("test.invalid")
    body["when"] = {"field": "x", "op": "bogus_op", "value": 1}
    r = client.post("/api/v1/rules", json=body)
    assert r.status_code == 422


def test_RU_PUT_updates_and_bumps_version(client):
    body = _create_body("test.update")
    r = client.post("/api/v1/rules", json=body)
    assert r.status_code == 200
    r2 = client.put("/api/v1/rules/test.update", json={
        "priority": 50,
        "title": "Updated title",
    })
    assert r2.status_code == 200
    detail = r2.json()
    assert detail["priority"] == 50
    assert detail["title"] == "Updated title"
    assert detail["version"] == "1.1.0"  # minor bump
    client.delete("/api/v1/rules/test.update")


def test_RU_PUT_archived_rule_returns_400(client):
    body = _create_body("test.archived")
    r = client.post("/api/v1/rules", json=body)
    assert r.status_code == 200
    # Force into archived by approving then archiving a subsequent edit
    # — but it's simpler to just set the file's status directly via the
    # repo. We test the API rejection path by submitting + approving so
    # the rule becomes active, then trying to PUT.
    r = client.post("/api/v1/rules/test.archived/submit", json={"submittedBy": "tester"})
    assert r.status_code == 200
    r = client.post("/api/v1/rules/test.archived/approve",
                    json={"approver": "sme", "rationale": "ok"})
    assert r.status_code == 200
    # Now active — PUT should be rejected
    r = client.put("/api/v1/rules/test.archived", json={"title": "should fail"})
    assert r.status_code == 400
    assert "active" in r.json()["detail"]
    client.delete("/api/v1/rules/test.archived")


def test_RU_DELETE_bootstrap_requires_force(client):
    r = client.delete("/api/v1/rules/freshness.library.expired")
    assert r.status_code == 400
    assert "bootstrap" in r.json()["detail"]
    # force=true wins
    r2 = client.delete("/api/v1/rules/freshness.library.expired?force=true")
    assert r2.status_code == 200


# ════════════════════════════════════════════════════════════════════
# Lifecycle: submit → approve / reject
# ════════════════════════════════════════════════════════════════════

def test_RU_SUBMIT_draft_to_pending_review(client):
    body = _create_body("test.submit")
    client.post("/api/v1/rules", json=body)
    r = client.post("/api/v1/rules/test.submit/submit", json={"submittedBy": "alice"})
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status"] == "pending_review"
    assert detail["submittedBy"] == "alice"
    assert detail["reviewQueue"] == "ops"
    client.delete("/api/v1/rules/test.submit")


def test_RU_SUBMIT_non_draft_returns_400(client):
    # Pick a seeded rule that survives every test in this module (no test
    # deletes this one). It's status=active, so submit must 400.
    r = client.post("/api/v1/rules/approval.halt.pii/submit",
                    json={"submittedBy": "alice"})
    assert r.status_code == 400


def test_RU_APPROVE_pending_to_active(client):
    body = _create_body("test.approve")
    client.post("/api/v1/rules", json=body)
    client.post("/api/v1/rules/test.approve/submit", json={"submittedBy": "alice"})
    r = client.post("/api/v1/rules/test.approve/approve",
                    json={"approver": "bob", "rationale": "looks good"})
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status"] == "active"
    assert detail["approvedBy"] == "bob"
    assert detail["rationale"] == "looks good"
    assert detail["approvedAt"]
    client.delete("/api/v1/rules/test.approve?force=true")


def test_RU_APPROVE_non_pending_returns_400(client):
    body = _create_body("test.approve_bad")
    client.post("/api/v1/rules", json=body)
    r = client.post("/api/v1/rules/test.approve_bad/approve",
                    json={"approver": "x", "rationale": "x"})
    assert r.status_code == 400
    client.delete("/api/v1/rules/test.approve_bad")


def test_RU_REJECT_pending_back_to_draft(client):
    body = _create_body("test.reject")
    client.post("/api/v1/rules", json=body)
    client.post("/api/v1/rules/test.reject/submit", json={"submittedBy": "alice"})
    r = client.post("/api/v1/rules/test.reject/reject",
                    json={"approver": "bob", "rationale": "regex too broad"})
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status"] == "draft"
    assert detail["rationale"] == "regex too broad"
    client.delete("/api/v1/rules/test.reject")


# ════════════════════════════════════════════════════════════════════
# Queue endpoint
# ════════════════════════════════════════════════════════════════════

def test_RU_QUEUE_returns_only_pending(client):
    body = _create_body("test.queue1")
    client.post("/api/v1/rules", json=body)
    client.post("/api/v1/rules/test.queue1/submit", json={"submittedBy": "alice"})

    body2 = _create_body("test.queue2", engine="approval",
                         when={"field": "validate_verdict", "op": "eq", "value": "halt"},
                         then={"route": "halt", "queue": "legal", "rationale": "x"})
    client.post("/api/v1/rules", json=body2)
    client.post("/api/v1/rules/test.queue2/submit", json={"submittedBy": "bob"})

    r = client.get("/api/v1/rules/queue")
    assert r.status_code == 200
    ids = {d["ruleId"] for d in r.json()}
    assert "test.queue1" in ids and "test.queue2" in ids
    for d in r.json():
        assert d["status"] == "pending_review"

    # Cleanup
    client.delete("/api/v1/rules/test.queue1")
    client.delete("/api/v1/rules/test.queue2")


# ════════════════════════════════════════════════════════════════════
# Validate + evaluate dry-run
# ════════════════════════════════════════════════════════════════════

def test_RU_VALIDATE_good_dsl(client):
    r = client.post("/api/v1/rules/validate", json={
        "when": {"field": "tags", "op": "contains", "value": "x"},
    })
    assert r.status_code == 200
    assert r.json() == {"ok": True, "errors": []}


def test_RU_VALIDATE_bad_dsl(client):
    r = client.post("/api/v1/rules/validate", json={
        "when": {"field": "x", "op": "no_such", "value": 1},
    })
    body = r.json()
    assert body["ok"] is False
    assert any("unknown op" in e["msg"] for e in body["errors"])


def test_RU_EVALUATE_dry_run(client):
    r = client.post("/api/v1/rules/freshness.library.bootstrap_tag/evaluate", json={
        "context": {"library_entry": {"tags": ["bootstrap", "ops"]}},
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fired"] is True
    assert "bootstrap" in body["verdict"]["reason"]


def test_RU_EVALUATE_no_match(client):
    r = client.post("/api/v1/rules/approval.halt.pii/evaluate", json={
        "context": {"pii_halt": False},
    })
    assert r.status_code == 200
    assert r.json()["fired"] is False
