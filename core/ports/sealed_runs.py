"""
SealedRunsRepository Protocol — read side of L01.

Every sealed run + DDQ packet the orchestrator writes is the source of truth
for everything the UI shows. The orchestrator (apps/orchestrator/main.py) is
the write side: it stamps Merkle-rooted, hash-chained journals to S3 (Object
Lock) and mirrors them to `data/manifests/runs/` + `data/manifests/inbox/`
for local-dev consumption.

This port is the read side. The API gateway depends on it; an `fs_` adapter
serves dev today, an `s3_` adapter lands when LocalStack/Object-Lock parity
is verified.

Shapes returned are the sealed JSON dicts written by the orchestrator —
schemas live alongside `apps/orchestrator/main.py`.
"""

from __future__ import annotations

from typing import Optional, Protocol


class SealedRunsRepository(Protocol):
    def list_run_ids(self) -> list[str]: ...
    def get_sealed_run(self, run_id: str) -> Optional[dict]: ...
    def list_ddq_ids(self) -> list[str]: ...
    def get_sealed_packet(self, ddq_id: str) -> Optional[dict]: ...
