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

from infra.adapters.fs_audit_dataset import FsAuditDataset
from infra.adapters.fs_canonical import FsCanonical
from infra.adapters.fs_knowledge import FsKnowledge
from infra.adapters.fs_manifests import FsManifests
from infra.adapters.fs_prompts import FsPrompts
from infra.adapters.fs_rules import FsRules
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
        self.knowledge = FsKnowledge(settings.manifests_dir)
        self.canonical = FsCanonical(settings.manifests_dir)
        self.audit_dataset = FsAuditDataset(self.runs, settings.manifests_dir)
        self.mongo: Optional[Any] = None
        self.lib: Optional[Any] = None
        self.tax: Optional[Any] = None
        # Rule engine: prefer Mongo when available, fall back to FS.
        # FS-mode rules live under data/manifests/rules/ and are seeded
        # by data/bootstrap/seed_rules.py on first dev boot. When Mongo
        # is the chosen store but its collection is empty (fresh stack),
        # copy the FS bootstrap rules in so the API never serves [].
        fs_rules = FsRules(settings.manifests_dir)
        self.rules: Any = fs_rules
        if settings.use_mongo:
            self.mongo, self.lib, self.tax = _build_mongo(settings)
            if self.mongo is not None:
                try:
                    from infra.adapters.mongo_rules import MongoRules
                    mongo_rules = MongoRules(self.mongo)
                    if not any(mongo_rules.list_all()):
                        for r in fs_rules.list_all():
                            mongo_rules.upsert(r)
                    self.rules = mongo_rules
                except Exception:
                    # Mongo adapter import/init failure is non-fatal; FsRules
                    # stays as the live engine for this container.
                    pass
        self._s3: Optional[Any] = None
        self._cors_ensured = False

    def s3(self):
        """Lazy boto3 S3 client pointing at LocalStack (shared with bootstrap)."""
        if self._s3 is None:
            from data.bootstrap._lib import s3_client
            self._s3 = s3_client()
        return self._s3

    def ensure_knowledge_uploads_cors(self) -> None:
        """Idempotently set CORS on the knowledge-raw bucket so the browser
        can PUT presigned URLs. LocalStack `localstack-init.sh` also sets
        this for fresh containers; the runtime call covers existing dev
        stacks that came up before the script learned about CORS.

        Allow-origin is wildcard for the dev bucket: Vite picks the next
        free port when its default (5173) is taken (and the dataset e2e
        suite uses 5175), so exact-match origins don't survive port drift.
        LocalStack is local-only — there's no exposure beyond the dev
        machine. Real S3 + Object Lock in M1 should constrain this back."""
        if self._cors_ensured:
            return
        rules = [{
            "AllowedHeaders": ["*"],
            "AllowedMethods": ["PUT", "GET", "HEAD"],
            "AllowedOrigins": ["*"],
            "ExposeHeaders": ["ETag"],
            "MaxAgeSeconds": 3600,
        }]
        try:
            self.s3().put_bucket_cors(
                Bucket=self.settings.knowledge_raw_bucket,
                CORSConfiguration={"CORSRules": rules},
            )
            self._cors_ensured = True
        except Exception:
            # Don't fail the request if CORS setup hiccups — surfaces as a
            # browser-side CORS error which the operator can diagnose.
            pass


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
