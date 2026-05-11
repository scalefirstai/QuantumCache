"""Agent protocol + RunContext — ddq.md §L06.

Every agent in the L06 roster implements this protocol. Inputs and outputs
are Pydantic models from packages.schemas.agents; JSON-serializable so the
audit journal can hash + replay them.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _short_hash(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass
class AgentEvent:
    """One step in the run journal. Hash-chained downstream per L01."""
    event_id: str
    kind: str                            # "agent.<name>.invoke", "agent.<name>.result"
    agent: str
    agent_version: str
    ts: str
    payload: dict
    payload_hash: str

    @classmethod
    def make(cls, agent: str, version: str, kind: str, payload: dict) -> "AgentEvent":
        import uuid
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return cls(
            event_id="evt_" + uuid.uuid4().hex[:16],
            kind=kind,
            agent=agent,
            agent_version=version,
            ts=_now(),
            payload=payload,
            payload_hash=_short_hash(body),
        )


@dataclass
class RunContext:
    """Shared run-scoped context handed to every agent."""
    run_id: str
    taxonomy_version: str
    library_version: str
    platform_version: str
    entity: str
    events: list[AgentEvent] = field(default_factory=list)

    def emit(self, ev: AgentEvent) -> None:
        self.events.append(ev)


class Agent(Protocol):
    """ddq.md §L06 — every agent implements this contract."""
    name: str
    version: str

    def run(self, agent_input: Any, ctx: RunContext) -> Any: ...
