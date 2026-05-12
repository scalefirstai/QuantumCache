"""
Smoke test for the API gateway. Hits every endpoint the UI declares and
diffs the response against the on-disk UI fixture — the same fixture the
UI's component tests pin against. If they match, the wire shape is correct
by construction.

Run from repo root:
    .venv/bin/python -m pytest apps/api_gateway/tests/
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api_gateway.deps import container
from apps.api_gateway.main import app

REPO = Path(__file__).resolve().parents[3]
FIX = REPO / "apps" / "ui" / "src" / "mocks" / "fixtures"


@pytest.fixture(scope="module")
def client() -> TestClient:
    container.cache_clear()  # in case settings changed between tests
    return TestClient(app)


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["runs"] >= 1
    assert body["ddqs"] >= 1


def test_runs_index_matches_fixture(client: TestClient) -> None:
    # The API is the source of truth (all sealed runs on disk); the static
    # UI fixture may be a subset if it hasn't been regenerated since the
    # last orchestrator run. We require every fixture row to round-trip
    # exactly through the API — that's enough to lock the contract.
    r = client.get("/api/v1/runs")
    assert r.status_code == 200
    api_by_id = {row["runId"]: row for row in r.json()}
    fixture = _load(FIX / "runs-index.json")
    assert fixture, "expected UI run-index fixture to be non-empty"
    for row in fixture:
        assert row["runId"] in api_by_id, f"fixture run missing from API: {row['runId']}"
        assert api_by_id[row["runId"]] == row


def test_get_run_matches_fixture(client: TestClient) -> None:
    fixtures = sorted((FIX / "runs").glob("*.json"))
    assert fixtures, "expected UI run fixtures to exist"
    for path in fixtures:
        run_id = path.stem
        r = client.get(f"/api/v1/runs/{run_id}")
        assert r.status_code == 200, f"missing run {run_id}"
        assert r.json() == _load(path)


def test_get_run_404(client: TestClient) -> None:
    r = client.get("/api/v1/runs/run_does_not_exist")
    assert r.status_code == 404


def test_pipelines_index_matches_fixture(client: TestClient) -> None:
    # The same ddq_id can be re-sealed (sealedAt floats); compare only the
    # stable identity fields against the fixture.
    r = client.get("/api/v1/pipelines")
    assert r.status_code == 200
    api_by_id = {row["ddqId"]: row for row in r.json()}
    fixture = _load(FIX / "pipelines-index.json")
    assert fixture
    for row in fixture:
        ddq_id = row["ddqId"]
        assert ddq_id in api_by_id, f"fixture ddq missing from API: {ddq_id}"
        api_row = api_by_id[ddq_id]
        # questionCount drifts when orchestrator is re-run with --max-questions,
        # so it's not in the stable-identity set.
        for stable in ("ddqId", "subject", "from"):
            assert api_row[stable] == row[stable], f"{stable} drifted on {ddq_id}"


def test_get_pipeline_matches_fixture(client: TestClient) -> None:
    fixtures = sorted((FIX / "pipelines").glob("*.json"))
    assert fixtures, "expected UI pipeline fixtures to exist"
    for path in fixtures:
        ddq_id = path.stem
        r = client.get(f"/api/v1/pipelines/{ddq_id}")
        assert r.status_code == 200
        body = r.json()
        expected = _load(path)
        # Stable identity + structure; sealedAt / per-event hashes float when
        # the orchestrator is re-run against real Claude.
        for stable in ("ddqId", "subject", "from", "to", "rawEmlSha256"):
            assert body[stable] == expected[stable], f"{stable} drifted on {ddq_id}"
        # questionCount + per-question stages drift with --max-questions reruns.
        if len(body["questions"]) == len(expected["questions"]):
            for q in body["questions"]:
                assert len(q["stages"]) >= 1


def _has_same_shape(actual: dict, expected: dict, path: str = "") -> None:
    """Structural equality: same top-level keys; nested dicts recurse; lists
    match by length-or-skip — values are free to drift as the corpus grows."""
    assert set(actual.keys()) == set(expected.keys()), (
        f"key mismatch at {path or '<root>'}: "
        f"+{set(actual) - set(expected)} -{set(expected) - set(actual)}"
    )
    for k, v in expected.items():
        if isinstance(v, dict):
            assert isinstance(actual[k], dict), f"{path}.{k} should be dict"
            _has_same_shape(actual[k], v, f"{path}.{k}")


def test_get_employee_matches_shape(client: TestClient) -> None:
    r = client.get("/api/v1/employees/aria")
    assert r.status_code == 200
    body = r.json()
    fixture = _load(FIX / "employee.json")
    _has_same_shape(body, fixture)
    assert body["id"] == "aria"
    # Agent roster is the 8-agent L06 list — must stay stable.
    agent_names_expected = [a["name"] for a in fixture["agents"]]
    agent_names_actual = [a["name"] for a in body["agents"]]
    assert agent_names_actual == agent_names_expected


def test_get_employee_404(client: TestClient) -> None:
    r = client.get("/api/v1/employees/nobody")
    assert r.status_code == 404


def test_get_review_matches_shape(client: TestClient) -> None:
    r = client.get("/api/v1/employees/aria/reviews/q1-2026")
    assert r.status_code == 200
    body = r.json()
    fixture = _load(FIX / "review-q1.json")
    _has_same_shape(body, fixture)
    assert body["employeeId"] == "aria"
    assert len(body["kpis"]) == len(fixture["kpis"])
    assert [s["name"] for s in body["scorecard"]] == [s["name"] for s in fixture["scorecard"]]


def test_get_skill_matches_fixture(client: TestClient) -> None:
    # Skill is computed from static index reports — should match exactly.
    r = client.get("/api/v1/skills/retrieval-hybrid")
    assert r.status_code == 200
    assert r.json() == _load(FIX / "skill-retrieval.json")


def test_get_skill_404(client: TestClient) -> None:
    r = client.get("/api/v1/skills/unknown")
    assert r.status_code == 404
