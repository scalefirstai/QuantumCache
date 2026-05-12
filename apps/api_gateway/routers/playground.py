"""
Playground — fire a single question through the real orchestrator.

  POST /api/v1/playground/runs       → { runId: "pg_..." }
  GET  /api/v1/playground/runs/{id}  → PlaygroundRun

A POST synthesises a one-question .eml (CSV-attached) into a tmpdir, then
spawns `apps.orchestrator.main` as a subprocess so the playground takes
*exactly* the same code path as a production intake. Status is tracked
in-memory and reconciled against the sealed runs S3 bucket — when the
orchestrator writes a sealed_packet.json, we look up the per-question
run_id and link the playground run to it.

In-memory tracking is fine for M1 (single uvicorn worker). M2 swaps the
dict for Redis when we add horizontal scaling.
"""

from __future__ import annotations

import csv
import email.message
import email.utils
import io
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..deps import container

router = APIRouter(prefix="/api/v1/playground", tags=["playground"])


# Status singleton — survives within a single uvicorn worker.
_STATE_LOCK = threading.Lock()
_STATE: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_eml(question: str, framework: str, ddq_id: str) -> bytes:
    """Build a minimal one-question .eml the email intake parser will accept."""
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow(["question_id", "framework", "question"])
    writer.writerow(["PG-1", framework, question])
    csv_body = csv_buf.getvalue()

    msg = email.message.EmailMessage()
    msg["From"] = "Playground <playground@quantumcache.local>"
    msg["To"] = "ddq.intake@bny.com"
    msg["Subject"] = f"Playground · {ddq_id}"
    msg["Date"] = email.utils.formatdate(localtime=False, usegmt=True)
    msg["Message-ID"] = email.utils.make_msgid(domain="quantumcache.local")
    msg.set_content(f"Single-question playground submission.\n\n{question}\n")
    msg.add_attachment(
        csv_body.encode("utf-8"),
        maintype="text", subtype="csv",
        filename=f"{ddq_id}.csv",
    )
    return bytes(msg)


def _run_orchestrator_subprocess(
    repo_root: Path, eml_path: Path, pg_run_id: str
) -> None:
    """Spawn the orchestrator and reconcile with the sealed bucket on exit."""
    env = os.environ.copy()
    cmd = [
        str(repo_root / ".venv" / "bin" / "python"), "-m", "apps.orchestrator.main",
        "--eml", str(eml_path), "--max-questions", "1",
    ]
    log_path = eml_path.parent / "orchestrator.log"
    with log_path.open("wb") as log:
        proc = subprocess.run(
            cmd, cwd=str(repo_root), stdout=log, stderr=subprocess.STDOUT, env=env,
        )
    with _STATE_LOCK:
        entry = _STATE.setdefault(pg_run_id, {})
        entry["completedAt"] = _now()
        if proc.returncode != 0:
            entry["status"] = "failed"
            try:
                tail = log_path.read_text(errors="replace").splitlines()[-30:]
            except OSError:
                tail = []
            entry["error"] = "\n".join(tail)
            return
        # Find the sealed run. Per-question run files are sorted by ts in
        # data/manifests/runs/; pick the newest one written after submitTs.
        runs_dir = repo_root / "data" / "manifests" / "runs"
        latest = max(
            (p for p in runs_dir.glob("run_*.json")),
            key=lambda p: p.stat().st_mtime,
            default=None,
        )
        if latest is None:
            entry["status"] = "failed"
            entry["error"] = "Orchestrator exited 0 but no sealed run found."
            return
        entry["sealedRunId"] = latest.stem
        entry["status"] = "succeeded"


class SubmitBody(BaseModel):
    question: str = Field(min_length=4, max_length=4000)
    framework: str = Field(default="CAIQ", max_length=64)
    actor: str = "playground"


@router.post("/runs")
def submit(body: SubmitBody) -> dict:
    """Queue a playground run and return its tracking id."""
    pg_id = "pg_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:6]
    c = container()
    repo_root = c.settings.repo_root

    # The orchestrator is heavy (torch, sentence-transformers, MongoClient,
    # OpenSearch, Anthropic). Refuse if the venv binary isn't there.
    venv_py = repo_root / ".venv" / "bin" / "python"
    if not venv_py.exists():
        raise HTTPException(500, f"Orchestrator venv missing at {venv_py}")

    work_dir = repo_root / "data" / "fixtures" / "playground" / pg_id
    work_dir.mkdir(parents=True, exist_ok=True)
    eml_path = work_dir / "input.eml"
    eml_path.write_bytes(_build_eml(body.question, body.framework, pg_id))

    with _STATE_LOCK:
        _STATE[pg_id] = {
            "runId": pg_id,
            "question": body.question,
            "framework": body.framework,
            "actor": body.actor,
            "status": "running",
            "submittedAt": _now(),
            "completedAt": None,
            "sealedRunId": None,
            "error": None,
        }
    threading.Thread(
        target=_run_orchestrator_subprocess,
        args=(repo_root, eml_path, pg_id),
        daemon=True,
    ).start()
    return {"runId": pg_id}


@router.get("/runs/{pg_run_id}")
def get_run(pg_run_id: str) -> dict:
    with _STATE_LOCK:
        entry = _STATE.get(pg_run_id)
    if not entry:
        raise HTTPException(404, f"Playground run not found: {pg_run_id}")
    return dict(entry)


@router.get("/runs")
def list_runs() -> list[dict]:
    """Recent submissions, newest first. Capped to last 50."""
    with _STATE_LOCK:
        entries = list(_STATE.values())
    entries.sort(key=lambda e: e["submittedAt"], reverse=True)
    return entries[:50]
