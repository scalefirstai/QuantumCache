"""
S3-backed SealedRunsRepository.

Reads the bucket the orchestrator writes to:
  s3://bny-ddq-runs-sealed/<run_id>/sealed.json
  s3://bny-ddq-runs-sealed/inbox/<ddq_id>/sealed_packet.json

Implements the same SealedRunsRepository protocol as fs_sealed_runs; choosing
the adapter is a startup-time config flip — see apps/api_gateway/deps.py.

Both LocalStack (dev) and real AWS (prod) work with the same code: the
client comes from `data.bootstrap._lib.s3_client()` which honours
AWS_ENDPOINT_URL (LocalStack) and falls back to the default AWS chain.
"""

from __future__ import annotations

import json
from typing import Any, Optional


class S3SealedRuns:
    def __init__(self, s3_client: Any, bucket: str = "bny-ddq-runs-sealed") -> None:
        self._s3 = s3_client
        self._bucket = bucket

    def _list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents") or []:
                keys.append(obj["Key"])
        return keys

    def _get_json(self, key: str) -> Optional[dict]:
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=key)
        except self._s3.exceptions.NoSuchKey:
            return None
        except Exception as exc:
            # NoSuchBucket / NotFound on first-boot when nothing's sealed yet.
            err_code = getattr(getattr(exc, "response", {}), "get", lambda *_: {})("Error", {}).get("Code")
            if err_code in {"NoSuchKey", "NoSuchBucket", "404"}:
                return None
            raise
        body = resp["Body"].read()
        return json.loads(body.decode("utf-8"))

    # --- SealedRunsRepository ---

    def list_run_ids(self) -> list[str]:
        ids: list[str] = []
        for key in self._list_keys(prefix="run_"):
            # Key shape: run_<ts>_<rand>/sealed.json
            head, _, tail = key.partition("/")
            if tail == "sealed.json" and head.startswith("run_"):
                ids.append(head)
        return sorted(ids)

    def get_sealed_run(self, run_id: str) -> Optional[dict]:
        return self._get_json(f"{run_id}/sealed.json")

    def list_ddq_ids(self) -> list[str]:
        ids: list[str] = []
        for key in self._list_keys(prefix="inbox/"):
            # Key shape: inbox/ddq_<id>/sealed_packet.json
            parts = key.split("/")
            if len(parts) == 3 and parts[2] == "sealed_packet.json":
                ids.append(parts[1])
        return sorted(ids)

    def get_sealed_packet(self, ddq_id: str) -> Optional[dict]:
        return self._get_json(f"inbox/{ddq_id}/sealed_packet.json")
