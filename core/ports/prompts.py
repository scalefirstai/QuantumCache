"""
PromptsRepository Protocol — read/write side of the L06 agent prompts.

Each LLM agent's instructions live as versioned files on disk
(services/<svc>/prompts/v<semver>.md). This port lets the API gateway
list / read / create / activate versions without depending on the
filesystem layout directly. A future MongoLibrary-backed adapter can
implement the same protocol once prompt edits need to flow through the
L05 library workflow (proposal → approval → seal).

Rule-based agents (FreshnessAuditor, ApprovalRouter) are not stored
here — they have no prompts. The router-level handlers surface them
with kind="rule" by reading the agent roster from disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class PromptDocument:
    agent_id: str
    agent_name: str
    version: str            # SemVer
    model: str
    temperature: float
    max_tokens: int
    description: str
    tools: tuple[str, ...]
    system: str
    user_template: str
    raw: str
    sha256: str


@dataclass(frozen=True)
class VersionSummary:
    version: str
    created_at: str
    is_active: bool
    sha256: str
    comment: Optional[str]


@dataclass(frozen=True)
class AuditEntry:
    ts: str
    actor: str
    action: str             # "create" | "activate"
    from_version: Optional[str]
    to_version: str
    comment: Optional[str]


class VersionConflict(RuntimeError):
    """Raised when a write was based on a stale active version."""

    def __init__(self, current_active: str, expected: str) -> None:
        super().__init__(
            f"Active version is {current_active}, write expected {expected}"
        )
        self.current_active = current_active
        self.expected = expected


class PromptsRepository(Protocol):
    def list_agent_ids(self) -> list[str]: ...
    def get_document(self, agent_id: str, version: Optional[str] = None) -> Optional[PromptDocument]: ...
    def list_versions(self, agent_id: str) -> list[VersionSummary]: ...
    def active_version(self, agent_id: str) -> Optional[str]: ...
    def create_version(
        self,
        agent_id: str,
        base_version: str,
        bump: str,
        system: str,
        user_template: str,
        model: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
        description: Optional[str],
        tools: Optional[list[str]],
        actor: str,
        comment: Optional[str],
        activate: bool,
        action_label: str = "create",
    ) -> PromptDocument: ...
    def set_active(
        self,
        agent_id: str,
        version: str,
        actor: str,
        comment: Optional[str],
    ) -> Optional[str]: ...
    def list_audit(self, agent_id: str) -> list[AuditEntry]: ...
