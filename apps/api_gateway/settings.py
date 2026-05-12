"""
API-gateway settings.

Driven by env vars so the same binary serves local dev (filesystem) and
M1+ live backends without code changes.

  DDQ_REPO_ROOT             absolute repo root; defaults to inferring from
                            this file's location (../..).
  DDQ_RUNS_DIR              override runs manifest dir. Default:
                            $REPO_ROOT/data/manifests/runs
  DDQ_INBOX_DIR             override inbox manifest dir. Default:
                            $REPO_ROOT/data/manifests/inbox
  DDQ_MANIFESTS_DIR         override aggregate manifest dir. Default:
                            $REPO_ROOT/data/manifests
  DDQ_EVALS_REPORTS_DIR     override eval-reports dir. Default:
                            $REPO_ROOT/evals/reports
  DDQ_CORS_ORIGINS          comma-separated list. Default: Vite dev server
                            on both localhost and 127.0.0.1 (browser treats
                            them as distinct origins for CORS).
  DDQ_RUNS_BACKEND          "s3" (default) or "fs". Selects where sealed
                            runs/packets are read from.
  DDQ_RUNS_BUCKET           S3 bucket for sealed runs. Default
                            "bny-ddq-runs-sealed".
  DDQ_KNOWLEDGE_RAW_BUCKET  S3 bucket for raw knowledge document bytes
                            (the operator-upload target). Default
                            "bny-ddq-knowledge-raw".
  DDQ_USE_MONGO             "1" to enrich /employees aggregates with live
                            Mongo state; "0" (default) keeps reports JSON.
  DDQ_MONGO_URI             Mongo connection string. Default
                            "mongodb://ddq:ddq-dev@localhost:27018".
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    env = os.environ.get("DDQ_REPO_ROOT")
    if env:
        return Path(env).resolve()
    # apps/api-gateway/settings.py → repo root is two parents up.
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    runs_dir: Path
    inbox_dir: Path
    manifests_dir: Path
    evals_reports_dir: Path
    cors_origins: tuple[str, ...]
    runs_backend: str           # "s3" | "fs"
    runs_bucket: str
    knowledge_raw_bucket: str
    use_mongo: bool
    mongo_uri: str


def load_settings() -> Settings:
    root = _repo_root()
    return Settings(
        repo_root=root,
        runs_dir=Path(os.environ.get("DDQ_RUNS_DIR", root / "data" / "manifests" / "runs")),
        inbox_dir=Path(os.environ.get("DDQ_INBOX_DIR", root / "data" / "manifests" / "inbox")),
        manifests_dir=Path(os.environ.get("DDQ_MANIFESTS_DIR", root / "data" / "manifests")),
        evals_reports_dir=Path(os.environ.get("DDQ_EVALS_REPORTS_DIR", root / "evals" / "reports")),
        cors_origins=tuple(
            o.strip()
            for o in os.environ.get(
                "DDQ_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if o.strip()
        ),
        runs_backend=os.environ.get("DDQ_RUNS_BACKEND", "s3").lower(),
        runs_bucket=os.environ.get("DDQ_RUNS_BUCKET", "bny-ddq-runs-sealed"),
        knowledge_raw_bucket=os.environ.get("DDQ_KNOWLEDGE_RAW_BUCKET", "bny-ddq-knowledge-raw"),
        use_mongo=os.environ.get("DDQ_USE_MONGO", "1") == "1",
        mongo_uri=os.environ.get("DDQ_MONGO_URI", "mongodb://ddq:ddq-dev@localhost:27018"),
    )
