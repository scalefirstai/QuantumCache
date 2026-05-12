"""
Adapter that imports the existing fixture-builder functions from
`data/bootstrap/12_build_ui_fixtures.py` and `13_build_pipeline_fixtures.py`.

The bootstrap scripts have leading digits in their filenames, so they can't
be imported via normal `import` syntax. We load them once via importlib and
expose the pure `build_*` functions the API needs.

Keeping the API in lock-step with the fixtures by *reusing* the same code
guarantees the wire shape stays identical — the existing UI tests pin to
the fixture output, so any drift is caught immediately.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load(repo_root: Path, filename: str, module_name: str) -> ModuleType:
    path = repo_root / "data" / "bootstrap" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load bootstrap module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FixtureBuilders:
    """Lazy bundle of `build_*` callables from the bootstrap scripts."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._ui: ModuleType | None = None
        self._pipeline: ModuleType | None = None

    def _ui_module(self) -> ModuleType:
        if self._ui is None:
            self._ui = _load(self._repo_root, "12_build_ui_fixtures.py", "_bootstrap_ui_fixtures")
        return self._ui

    def _pipeline_module(self) -> ModuleType:
        if self._pipeline is None:
            self._pipeline = _load(
                self._repo_root, "13_build_pipeline_fixtures.py", "_bootstrap_pipeline_fixtures"
            )
        return self._pipeline

    # --- /runs ---
    def build_run_view(self, sealed_run: dict) -> dict:
        return self._ui_module().build_run_view(sealed_run)

    def truncate(self, s: str, n: int) -> str:
        return self._ui_module()._truncate(s, n)

    # --- /employees & /reviews ---
    def build_employee(self, runs: list[dict], wire: dict, tx: dict, lib: dict) -> dict:
        return self._ui_module().build_employee(runs, wire, tx, lib)

    def build_review(
        self, runs: list[dict], wire: dict, eval_report: dict, tx: dict, lib: dict
    ) -> dict:
        return self._ui_module().build_review(runs, wire, eval_report, tx, lib)

    # --- /skills ---
    def build_skill(
        self, eval_report: dict, hybrid: list[dict], os_report: dict, qdrant_report: dict
    ) -> dict:
        return self._ui_module().build_skill(eval_report, hybrid, os_report, qdrant_report)

    # --- /pipelines ---
    def build_question(self, q_result: dict, sealed_run: dict) -> dict:
        return self._pipeline_module()._build_question(q_result, sealed_run)
