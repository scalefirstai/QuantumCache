"""Anthropic API adapter for LLMClient. ddq.md §L06.

Uses prompt caching on the system prompt by default — corpus context is
expensive to re-pay for; the system block is reused across many questions
in a single DDQ run.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, Optional

from anthropic import Anthropic

from packages.llm_sdk.port import (
    LLMClient, LLMRequest, LLMResponse, MODEL_FOR_TIER,
)


def load_api_key(env_path: Optional[Path] = None) -> str:
    """Read ANTHROPIC_KEY (or ANTROPIC_KEY misspelling) from .env or env vars."""
    env_path = env_path or Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k in ("ANTHROPIC_KEY", "ANTHROPIC_API_KEY", "ANTROPIC_KEY"):
                os.environ.setdefault("ANTHROPIC_API_KEY", v)
                return v
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_KEY")
    if not key:
        raise RuntimeError(
            "No Anthropic API key found in .env or environment "
            "(looked for ANTHROPIC_KEY / ANTROPIC_KEY / ANTHROPIC_API_KEY)"
        )
    return key


class AnthropicClient(LLMClient):
    def __init__(self, api_key: Optional[str] = None):
        self._client = Anthropic(api_key=api_key or load_api_key())

    def complete(self, req: LLMRequest) -> LLMResponse:
        model = MODEL_FOR_TIER[req.tier]
        system_blocks = [{
            "type": "text",
            "text": req.system,
            **({"cache_control": {"type": "ephemeral"}} if req.cache_system else {}),
        }]
        kwargs: dict = dict(
            model=model,
            max_tokens=req.max_tokens,
            system=system_blocks,
            messages=[{"role": "user", "content": req.user}],
        )
        # Opus 4.7 deprecated `temperature`. Sonnet 4.6 + Haiku 4.5 still accept it.
        if not model.startswith("claude-opus-4-7"):
            kwargs["temperature"] = req.temperature
        resp = self._client.messages.create(**kwargs)
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        usage = resp.usage
        return LLMResponse(
            text=text,
            model=resp.model,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            stop_reason=resp.stop_reason,
            raw={"id": resp.id},
        )

    def stream(self, req: LLMRequest) -> Iterator[str]:
        model = MODEL_FOR_TIER[req.tier]
        with self._client.messages.stream(
            model=model,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            system=req.system,
            messages=[{"role": "user", "content": req.user}],
        ) as stream:
            for chunk in stream.text_stream:
                yield chunk
