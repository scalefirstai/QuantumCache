"""CitationVerifier — ddq.md §L06.

Haiku-tier. For every `[span:<id>]` citation in the draft, fetches the
canonical span text and asks Claude whether the claim immediately preceding
the citation is genuinely supported. Returns the union check.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from core.ports.agent import Agent, AgentEvent, RunContext
from packages.llm_sdk import AnthropicClient, LLMClient, LLMRequest
from packages.prompts import resolve_active
from packages.schemas.agents import (
    CitationCheckResult, CitationVerifierInput, CitationVerifierOutput,
)


# Active prompt resolved per-call so UI edits land on the next orchestrator run.
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _render_prompt(input_: CitationVerifierInput, span_text_by_id: dict[str, str]) -> tuple[str, str]:
    raw = resolve_active(__file__).path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    body = parts[2] if len(parts) >= 3 else raw
    system_part, user_part = body.split("# User", 1)
    system_part = system_part.replace("# System", "").strip()

    lines = []
    for c in input_.citations:
        text = span_text_by_id.get(c.span_id) or "(span text unavailable)"
        lines.append(
            f"span_id={c.span_id}\n"
            f"  span_hash={c.span_hash}\n"
            f"  text: {text[:700]}"
        )
    citations_block = "\n\n".join(lines) or "(none)"

    user_rendered = (
        user_part.strip()
        .replace("{{draft_text}}", input_.draft_text.strip())
        .replace("{{citations_block}}", citations_block)
    )
    return system_part, user_rendered


def _parse(text: str) -> dict:
    m = _JSON_RE.search(text)
    if not m:
        return {"all_pass": False, "results": [], "summary": "no JSON in reply"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"all_pass": False, "results": [], "summary": "invalid JSON in reply"}


class CitationVerifier(Agent):
    name = "CitationVerifier"
    version = "1.0.0"

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or AnthropicClient()

    def run(self, agent_input: CitationVerifierInput, ctx: RunContext) -> CitationVerifierOutput:
        if not agent_input.citations:
            ctx.emit(AgentEvent.make(self.name, self.version, "agent.CitationVerifier.result", {
                "all_pass": False, "reason": "no citations in draft", "checked": 0,
            }))
            return CitationVerifierOutput(
                all_pass=False,
                results=[],
                summary="Draft has no citations — fails guardrail 01.",
            )

        # First: deterministic resolution check (span_hash must be in supplied lookup).
        results: list[CitationCheckResult] = []
        unresolved_hashes: list[str] = []
        for c in agent_input.citations:
            if c.span_hash in agent_input.span_lookup:
                results.append(CitationCheckResult(
                    span_hash=c.span_hash, resolved=True,
                    excerpt_matches_span=True, reason=None,
                ))
            else:
                unresolved_hashes.append(c.span_hash)
                results.append(CitationCheckResult(
                    span_hash=c.span_hash, resolved=False,
                    excerpt_matches_span=False,
                    reason="span_hash not found in current corpus snapshot",
                ))

        # Second: semantic "claim → span" check via Claude over resolved spans.
        span_text_by_id = {
            c.span_id: agent_input.span_lookup.get(c.span_hash, "")
            for c in agent_input.citations
        }
        system, user = _render_prompt(agent_input, span_text_by_id)
        req = LLMRequest(tier="tier3_haiku", system=system, user=user, max_tokens=800)
        ctx.emit(AgentEvent.make(self.name, self.version, "agent.CitationVerifier.invoke", {
            "citation_count": len(agent_input.citations),
            "unresolved_count": len(unresolved_hashes),
            "prompt_hash": req.prompt_hash(),
        }))
        resp = self.llm.complete(req)
        parsed = _parse(resp.text)

        # Merge semantic verdicts onto the resolution results.
        semantic_by_id = {r.get("span_id"): r for r in (parsed.get("results") or [])}
        merged: list[CitationCheckResult] = []
        for c, r0 in zip(agent_input.citations, results):
            sem = semantic_by_id.get(c.span_id, {})
            supports = bool(sem.get("supports_claim", False)) if r0.resolved else False
            reason = sem.get("reason") if r0.resolved else r0.reason
            merged.append(CitationCheckResult(
                span_hash=c.span_hash,
                resolved=r0.resolved,
                excerpt_matches_span=supports,
                reason=reason,
            ))
        all_pass = all(r.resolved and r.excerpt_matches_span for r in merged) if merged else False

        out = CitationVerifierOutput(
            all_pass=all_pass,
            results=merged,
            summary=str(parsed.get("summary", "")).strip()[:400],
        )
        ctx.emit(AgentEvent.make(self.name, self.version, "agent.CitationVerifier.result", {
            "all_pass": all_pass,
            "checked": len(merged),
            "unresolved": sum(1 for r in merged if not r.resolved),
            "unsupported": sum(1 for r in merged if r.resolved and not r.excerpt_matches_span),
            "response_hash": resp.response_hash(),
            "tokens": {"input": resp.input_tokens, "output": resp.output_tokens,
                       "cache_read": resp.cache_read_tokens},
        }))
        return out
