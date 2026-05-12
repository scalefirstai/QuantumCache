"""
Filesystem-backed ManifestsRepository.

Resolves well-known aggregate-manifest names to JSON files under
`data/manifests/` and `evals/reports/`. Unknown names return None so
callers can fall back gracefully.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class FsManifests:
    def __init__(self, manifests_dir: Path, evals_reports_dir: Path) -> None:
        # name → path. Add entries here when new aggregates land.
        self._paths: dict[str, Path] = {
            "wire-up":                 manifests_dir / "wire-up-report.json",
            "taxonomy":                manifests_dir / "taxonomy-v0.1-report.json",
            "library":                 manifests_dir / "library-v0.1-report.json",
            "hybrid-smoke":            manifests_dir / "hybrid-smoke-report.json",
            "opensearch-index":        manifests_dir / "opensearch-index-report.json",
            "qdrant-index":            manifests_dir / "qdrant-index-report.json",
            "eval-v0-baseline":        evals_reports_dir / "v0-baseline.json",
        }

    def get(self, name: str) -> Optional[dict]:
        path = self._paths.get(name)
        if path is None or not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
