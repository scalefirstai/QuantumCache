"""DraftComposer — ddq.md §L06.

Tier-routed: Opus 4.5 for tier-1 (regulatory / security control / financial
reporting), Sonnet 4.5 for tier-2 standard, Haiku 4.5 for tier-3 boilerplate.
The orchestrator decides the tier from canonical domain; this agent honors
the input.tier.
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
    CitationRef, DraftComposerInput, DraftComposerOutput,
)


# Active prompt resolved per-call so UI edits land on the next orchestrator run.


def _render_prompt(input_: DraftComposerInput) -> tuple[str, str]:
    raw = resolve_active(__file__).path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    body = parts[2] if len(parts) >= 3 else raw
    system_part, user_part = body.split("# User", 1)
    system_part = system_part.replace("# System", "").strip()

    lines = []
    for sp in input_.evidence_bundle:
        anchor = (f"page {sp.anchor_page}" if sp.anchor_kind == "page"
                  else (sp.anchor_item or "n/a"))
        excerpt = (sp.text or "").strip().replace("\n", " ")
        lines.append(
            f"span_id={sp.span_id}\n"
            f"  source={sp.source}  form={sp.form or '-'}  anchor={anchor}\n"
            f"  text: {excerpt[:700]}"
        )
    spans_block = "\n\n".join(lines) or "(none)"

    if input_.library_entry_text:
        library_block = (
            "LIBRARY ENTRY (authoritative phrasing — preserve closely):\n"
            f"  {input_.library_entry_text.strip()}\n"
        )
    else:
        library_block = "LIBRARY ENTRY: none — produce a fresh draft from the bundle."

    user_rendered = (
        user_part.strip()
        .replace("{{canonical_id}}", input_.canonical_id or "(unclassified)")
        .replace("{{tier}}", input_.tier)
        .replace("{{question_text}}", input_.raw_question_text.strip())
        .replace("{{library_block}}", library_block)
        .replace("{{n_spans}}", str(len(input_.evidence_bundle)))
        .replace("{{spans_block}}", spans_block)
    )
    return system_part, user_rendered


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_CITE_RE = re.compile(r"\[span:([^\]]+)\]")


def _parse(text: str) -> dict:
    m = _JSON_RE.search(text)
    if not m:
        return {"draft_text": text.strip(), "cited_span_ids": []}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"draft_text": text.strip(), "cited_span_ids": []}


class DraftComposer(Agent):
    name = "DraftComposer"
    version = "1.0.0"

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or AnthropicClient()

    def run(self, agent_input: DraftComposerInput, ctx: RunContext) -> DraftComposerOutput:
        if not agent_input.evidence_bundle and not agent_input.library_entry_text:
            ctx.emit(AgentEvent.make(self.name, self.version, "agent.DraftComposer.skip", {
                "reason": "no evidence and no library entry — handing off to SME",
            }))
            return DraftComposerOutput(
                draft_text="",
                citations=[],
                tier_used=agent_input.tier,
                used_library_entry=False,
            )

        system, user = _render_prompt(agent_input)
        req = LLMRequest(tier=agent_input.tier, system=system, user=user, max_tokens=1200)
        ctx.emit(AgentEvent.make(self.name, self.version, "agent.DraftComposer.invoke", {
            "question_id": agent_input.question_id,
            "canonical_id": agent_input.canonical_id,
            "tier": agent_input.tier,
            "evidence_count": len(agent_input.evidence_bundle),
            "used_library_entry": bool(agent_input.library_entry_text),
            "prompt_hash": req.prompt_hash(),
        }))
        resp = self.llm.complete(req)
        parsed = _parse(resp.text)

        draft_text = (parsed.get("draft_text") or "").strip()
        cited_ids = [str(s).strip() for s in (parsed.get("cited_span_ids") or [])]
        # Sanity: drop cite IDs that aren't actually inline in the draft.
        inline_ids = set(_CITE_RE.findall(draft_text))
        cited_ids = [c for c in cited_ids if c in inline_ids] or sorted(inline_ids)

        by_id = {s.span_id: s for s in agent_input.evidence_bundle}
        citations: list[CitationRef] = []
        for sid in cited_ids:
            sp = by_id.get(sid)
            if sp and sp.doc_hash and sp.span_hash:
                citations.append(CitationRef(
                    span_id=sid, doc_hash=sp.doc_hash, span_hash=sp.span_hash,
                    excerpt=(sp.text or "")[:240],
                ))

        out = DraftComposerOutput(
            draft_text=draft_text,
            citations=citations,
            tier_used=agent_input.tier,
            used_library_entry=bool(agent_input.library_entry_text),
        )
        ctx.emit(AgentEvent.make(self.name, self.version, "agent.DraftComposer.result", {
            "draft_chars": len(draft_text),
            "citation_count": len(citations),
            "cited_span_ids": [c.span_id for c in citations],
            "tier_used": out.tier_used,
            "response_hash": resp.response_hash(),
            "tokens": {"input": resp.input_tokens, "output": resp.output_tokens,
                       "cache_read": resp.cache_read_tokens},
        }))
        return out
