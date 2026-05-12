"""
ManifestsRepository Protocol — read-only access to bootstrap aggregate
manifests (taxonomy/library/wire-up/eval reports).

The /employees, /skills, and /reviews endpoints need data that isn't carried
on a single sealed run — they aggregate across runs and reference index/eval
state. The bootstrap pipeline writes a handful of well-known JSON files to
`data/manifests/` and `evals/reports/`. This port hides "where they live"
behind a named lookup so the API doesn't pin to filesystem paths.

When the real services land, taxonomy/library reports come from Mongo,
eval reports come from Langfuse, etc. — same names, new adapters.
"""

from __future__ import annotations

from typing import Optional, Protocol


class ManifestsRepository(Protocol):
    def get(self, name: str) -> Optional[dict]: ...
