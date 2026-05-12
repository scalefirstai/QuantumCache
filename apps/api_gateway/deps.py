"""
Dependency-injection wiring. One container is built at startup; routers
pull from it via `container()` (lru_cache=1).

Adapter selection is settings-driven:

  DDQ_RUNS_BACKEND=s3  → reads sealed runs/packets from LocalStack S3
                         (bucket = DDQ_RUNS_BUCKET, default
                         "bny-ddq-runs-sealed"). This is the live path
                         the orchestrator writes to.

  DDQ_RUNS_BACKEND=fs  → reads from data/manifests/runs/ +
                         data/manifests/inbox/. Useful when LocalStack
                         is down or for CI on a packaged snapshot.

  DDQ_USE_MONGO=1      → enriches /employees aggregates with live counts
                         from Mongo (ddq.library.entries,
                         ddq.taxonomy.questions) via the existing
                         MongoLibrary / MongoTaxonomy adapters.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from infra.adapters.fs_manifests import FsManifests
from infra.adapters.fs_prompts import FsPrompts
from infra.adapters.fs_sealed_runs import FsSealedRuns
from infra.adapters.s3_sealed_runs import S3SealedRuns

from .fixture_builders import FixtureBuilders
from .settings import Settings, load_settings


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.runs = _build_runs_repo(settings)
        self.manifests = FsManifests(settings.manifests_dir, settings.evals_reports_dir)
        self.prompts = FsPrompts(settings.repo_root / "services")
        self.builders = FixtureBuilders(settings.repo_root)
        self.mongo: Optional[Any] = None
        self.lib: Optional[Any] = None
        self.tax: Optional[Any] = None
        if settings.use_mongo:
            self.mongo, self.lib, self.tax = _build_mongo(settings)


def _build_runs_repo(settings: Settings):
    if settings.runs_backend == "s3":
        # Lazy import keeps fs-only deployments from pulling boto3.
        from data.bootstrap._lib import s3_client
        return S3SealedRuns(s3_client(), bucket=settings.runs_bucket)
    return FsSealedRuns(settings.runs_dir, settings.inbox_dir)


def _build_mongo(settings: Settings):
    """Optional Mongo wiring. Failures here are non-fatal — the API
    continues with reports-JSON only."""
    try:
        from pymongo import MongoClient
        from data.bootstrap._lib import s3_client
        from infra.adapters.mongo_library import MongoLibrary
        from infra.adapters.mongo_taxonomy import MongoTaxonomy
    except Exception:
        return None, None, None
    try:
        mongo = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=2000)
        mongo.admin.command("ping")
    except Exception:
        return None, None, None
    s3 = s3_client()
    return mongo, MongoLibrary(mongo, s3), MongoTaxonomy(mongo, s3)


@lru_cache(maxsize=1)
def container() -> Container:
    return Container(load_settings())
