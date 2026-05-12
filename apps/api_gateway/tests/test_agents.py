"""
AutoGen Lite — agent / model / skill / template / playground tests.

Each test runs against a tmp-path copy of services/ so writes don't
pollute the real repo. Spec: docs/autogen-lite.md.
"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def tmp_repo(tmp_path_factory) -> Iterator[Path]:
    base = tmp_path_factory.mktemp("repo")
    for sub in ("services", "data", "evals", "apps", "core", "infra", "packages"):
        src = REPO / sub
        if src.exists():
            shutil.copytree(src, base / sub, symlinks=False,
                            ignore=shutil.ignore_patterns("__pycache__"))
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


# ---- AG-01..AG-03 list/get -------------------------------------------------

def test_AG_01_list_agents(client):
    r = client.get("/api/v1/agents")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 8
    llms = [a for a in body if a["kind"] == "llm"]
    rules = [a for a in body if a["kind"] == "rule"]
    assert len(llms) == 6 and len(rules) == 2
    for a in llms:
        assert a["activeVersion"] == "1.0.0"
        assert a["model"].startswith("claude-")
        assert isinstance(a["tools"], list) and len(a["tools"]) >= 1
        assert a["temperature"] is not None
        assert a["maxTokens"] is not None


def test_AG_02_get_drafter_full_config(client):
    r = client.get("/api/v1/agents/drafter")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "drafter"
    assert body["kind"] == "llm"
    assert body["active"]["model"].startswith("claude-")
    assert "tools" in body["active"]
    assert "description" in body["active"]
    assert body["active"]["system"]
    assert body["active"]["userTemplate"]


def test_AG_03_rule_agent_active_none(client):
    body = client.get("/api/v1/agents/freshness").json()
    assert body["kind"] == "rule"
    assert body["active"] is None


# ---- AG-04..AG-06 create / conflict / activate -----------------------------

def test_AG_04_create_version_with_full_config(client):
    r = client.post("/api/v1/agents/drafter/versions", json={
        "baseVersion": "1.0.0",
        "bump": "patch",
        "system": "You are DraftComposer (AG-04).",
        "userTemplate": "Draft for {{question_id}}.",
        "temperature": 0.1,
        "maxTokens": 1500,
        "tools": ["llm.complete", "prompt.registry"],
        "actor": "pytest",
        "comment": "AG-04",
    })
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["version"] == "1.0.1"
    assert doc["temperature"] == 0.1
    assert doc["maxTokens"] == 1500
    assert doc["tools"] == ["llm.complete", "prompt.registry"]


def test_AG_05_stale_baseVersion_409(client):
    # Make 1.0.1 active so a base of 1.0.0 is stale.
    client.post("/api/v1/agents/drafter/versions", json={
        "baseVersion": "1.0.0", "bump": "patch",
        "system": "x", "userTemplate": "y",
        "actor": "pytest", "activate": True,
    })
    r = client.post("/api/v1/agents/drafter/versions", json={
        "baseVersion": "1.0.0", "bump": "patch",
        "system": "stale", "userTemplate": "y", "actor": "pytest",
    })
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "version_conflict"


def test_AG_06_activate_currentNoop_unknown404(client):
    summary = client.get("/api/v1/agents/drafter").json()
    active = summary["activeVersion"]
    before = client.get("/api/v1/agents/drafter/audit").json()
    r = client.put("/api/v1/agents/drafter/active", json={"version": active, "actor": "pytest"})
    assert r.status_code == 200
    assert client.get("/api/v1/agents/drafter/audit").json() == before
    r = client.put("/api/v1/agents/drafter/active", json={"version": "99.99.99"})
    assert r.status_code == 404


# ---- AG-07 templates -------------------------------------------------------

def test_AG_07_apply_template(client):
    r = client.post("/api/v1/agents/drafter/apply-template", json={
        "templateId": "conservative-compliance",
        "actor": "pytest",
    })
    assert r.status_code == 200, r.text
    doc = r.json()
    # patch sets temperature=0 and maxTokens=1024, appends a systemSuffix
    assert doc["temperature"] == 0.0
    assert doc["maxTokens"] == 1024
    assert "Reject any draft" in doc["system"]
    # Active should now be the new version (activate defaults True).
    summary = client.get("/api/v1/agents/drafter").json()
    assert summary["activeVersion"] == doc["version"]


# ---- AG-08 audit ordering --------------------------------------------------

def test_AG_08_audit_newest_first(client):
    audit = client.get("/api/v1/agents/drafter/audit").json()
    assert len(audit) >= 1
    for i in range(len(audit) - 1):
        assert audit[i]["ts"] >= audit[i + 1]["ts"]


# ---- AG-09 bad-id propagation ---------------------------------------------

def test_AG_09_bad_agent_id_404(client):
    for path in [
        "/api/v1/agents/zzz",
        "/api/v1/agents/zzz/versions",
        "/api/v1/agents/zzz/audit",
    ]:
        assert client.get(path).status_code == 404
    r = client.post("/api/v1/agents/zzz/apply-template", json={"templateId": "x"})
    assert r.status_code == 404


# ---- AG-10 atomic activate -------------------------------------------------

def test_AG_10_concurrent_activate_no_corruption(client):
    versions: list[str] = []
    base = client.get("/api/v1/agents/drafter").json()["activeVersion"]
    for _ in range(3):
        doc = client.post("/api/v1/agents/drafter/versions", json={
            "baseVersion": base, "bump": "patch",
            "system": "x", "userTemplate": "y", "actor": "pytest",
            "activate": True,
        }).json()
        base = doc["version"]
        versions.append(base)

    def flip(v):
        for _ in range(10):
            client.put("/api/v1/agents/drafter/active", json={"version": v})

    threads = [threading.Thread(target=flip, args=(v,)) for v in versions]
    for t in threads: t.start()
    for t in threads: t.join()

    final = client.get("/api/v1/agents/drafter").json()["activeVersion"]
    assert final in versions


# ---- Models / Skills / Templates -----------------------------------------

def test_MD_01_list_models(client):
    body = client.get("/api/v1/models").json()
    ids = {m["id"] for m in body}
    assert {"claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"} <= ids
    opus = next(m for m in body if m["id"] == "claude-opus-4-7")
    assert opus["contextWindow"] >= 200_000


def test_SK_01_list_skills(client):
    body = client.get("/api/v1/skills").json()
    by_id = {s["id"]: s for s in body}
    assert "retrieval.hybrid" in by_id
    # EvidenceSourcer's default toolset includes retrieval.hybrid.
    assert "EvidenceSourcer" in by_id["retrieval.hybrid"]["usedBy"]


def test_TM_01_list_templates(client):
    body = client.get("/api/v1/templates").json()
    ids = {t["id"] for t in body}
    assert {"conservative-compliance", "fast-cheap"} <= ids


# ---- Playground ------------------------------------------------------------

@pytest.mark.skip(
    reason="Playground submission requires the orchestrator's full live stack "
           "(.venv + LocalStack S3 + Mongo + OpenSearch + Qdrant + Anthropic) and "
           "is exercised by the live Playwright e2e suite (UI-PG-01 / UI-PG-02)."
)
def test_PG_01_submit_returns_run_id(client):
    r = client.post("/api/v1/playground/runs", json={
        "question": "Is multi-factor authentication enforced?",
        "framework": "CAIQ",
    })
    assert r.status_code == 200


def test_PG_02_unknown_playground_run_404(client):
    r = client.get("/api/v1/playground/runs/pg_does_not_exist")
    assert r.status_code == 404
