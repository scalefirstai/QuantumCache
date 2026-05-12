"""
Filesystem-backed SealedRunsRepository.

Reads the JSON the orchestrator already mirrors to:
  data/manifests/runs/run_*.json
  data/manifests/inbox/ddq_*.json

Suitable for local dev and CI smoke tests. An S3 adapter (live LocalStack
or production AWS) implements the same port without touching call sites.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class FsSealedRuns:
    def __init__(self, runs_dir: Path, inbox_dir: Path) -> None:
        self._runs_dir = runs_dir
        self._inbox_dir = inbox_dir

    def list_run_ids(self) -> list[str]:
        if not self._runs_dir.exists():
            return []
        return sorted(p.stem for p in self._runs_dir.glob("run_*.json"))

    def get_sealed_run(self, run_id: str) -> Optional[dict]:
        path = self._runs_dir / f"{run_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_ddq_ids(self) -> list[str]:
        if not self._inbox_dir.exists():
            return []
        return sorted(p.stem for p in self._inbox_dir.glob("ddq_*.json"))

    def get_sealed_packet(self, ddq_id: str) -> Optional[dict]:
        path = self._inbox_dir / f"{ddq_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
