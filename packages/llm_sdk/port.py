"""LLMClient port — ddq.md §L06.

Bedrock and Anthropic API are interchangeable adapters behind this port.
Every prompt+response is journaled with prompt_hash + response_hash so the
audit chain can replay deterministically.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Iterator, Literal, Optional, Protocol


ModelTier = Literal["tier1_opus", "tier2_sonnet", "tier3_haiku"]


# Canonical model IDs per ddq.md §L06 + system context.
MODEL_FOR_TIER: dict[ModelTier, str] = {
    "tier1_opus":   "claude-opus-4-7",
    "tier2_sonnet": "claude-sonnet-4-6",
    "tier3_haiku":  "claude-haiku-4-5",
}


@dataclass
class LLMRequest:
    tier: ModelTier
    system: str                          # rendered system prompt
    user: str                            # rendered user prompt
    max_tokens: int = 1024
    temperature: float = 0.0
    cache_system: bool = True            # use ephemeral cache breakpoint on system
    extra: dict = field(default_factory=dict)

    def prompt_hash(self) -> str:
        body = json.dumps({
            "tier": self.tier, "system": self.system, "user": self.user,
            "max_tokens": self.max_tokens, "temperature": self.temperature,
            "extra": self.extra,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "sha256:" + hashlib.sha256(body).hexdigest()


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    stop_reason: Optional[str] = None
    raw: dict = field(default_factory=dict)

    def response_hash(self) -> str:
        body = json.dumps({"text": self.text, "model": self.model,
                           "stop_reason": self.stop_reason},
                          sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "sha256:" + hashlib.sha256(body).hexdigest()


class LLMClient(Protocol):
    def complete(self, req: LLMRequest) -> LLMResponse: ...
    def stream(self, req: LLMRequest) -> Iterator[str]: ...
