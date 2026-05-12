"""
GET /api/v1/models  →  Model[]

Static registry of the Claude tiers the orchestrator wires to via
packages.llm_sdk.AnthropicClient. Hand-maintained until provider metadata
is dynamic — for now this matches the values used by the orchestrator's
tier dispatch in services/drafter/agent.py.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/models", tags=["models"])

MODELS: list[dict] = [
    {
        "id": "claude-opus-4-7",
        "displayName": "Claude Opus 4.7",
        "provider": "Anthropic",
        "tier": "tier1",
        "contextWindow": 1_000_000,
        "supportsTools": True,
        "supportsThinking": True,
        "pricing": {"inputPerMTok": 15.0, "outputPerMTok": 75.0},
        "notes": "Highest quality. Used by DraftComposer for tier-1 (regulated / cyber) canonicals.",
    },
    {
        "id": "claude-sonnet-4-6",
        "displayName": "Claude Sonnet 4.6",
        "provider": "Anthropic",
        "tier": "tier2",
        "contextWindow": 200_000,
        "supportsTools": True,
        "supportsThinking": True,
        "pricing": {"inputPerMTok": 3.0, "outputPerMTok": 15.0},
        "notes": "Default for EvidenceSourcer / ConsistencyChecker / DraftComposer tier-2.",
    },
    {
        "id": "claude-haiku-4-5",
        "displayName": "Claude Haiku 4.5",
        "provider": "Anthropic",
        "tier": "tier3",
        "contextWindow": 200_000,
        "supportsTools": True,
        "supportsThinking": False,
        "pricing": {"inputPerMTok": 1.0, "outputPerMTok": 5.0},
        "notes": "Cheap+fast classification. Used by QuestionMapper / CitationVerifier / PiiScrubber.",
    },
]


@router.get("")
def list_models() -> list[dict]:
    return MODELS
