"""RuleRepository protocol — the contract every storage adapter implements.

Two adapters today:
  - infra/adapters/fs_rules.py     filesystem (dev + tests)
  - infra/adapters/mongo_rules.py  Mongo (production)

The agent re-wires in services/freshness/agent.py + services/router/agent.py
accept any object that satisfies this protocol; the API gateway picks one
based on `DDQ_USE_MONGO`.
"""

from __future__ import annotations

from typing import Iterator, Optional, Protocol

from core.domain.rules import Rule, RuleEngine, RuleStatus


class RuleRepository(Protocol):
    def upsert(self, rule: Rule) -> None: ...
    def get(self, rule_id: str) -> Optional[Rule]: ...
    def list_all(
        self,
        *,
        engine: Optional[RuleEngine] = None,
        status: Optional[RuleStatus] = None,
    ) -> Iterator[Rule]: ...
    def get_active(self, engine: RuleEngine) -> list[Rule]: ...
    def delete(self, rule_id: str, *, force: bool = False) -> bool: ...
    def last_updated_at(self) -> Optional[str]: ...
