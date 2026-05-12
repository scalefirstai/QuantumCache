"""EvidenceSourcer — ddq.md §L06.

Sonnet-tier curator. Takes the hybrid-retrieval candidate set from the
orchestrator and selects the subset that genuinely answers the question.
Never drafts prose.
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
    EvidenceSourcerInput, EvidenceSourcerOutput, EvidenceSpan,
)


# Active prompt resolved per-call so UI edits land on the next orchestrator run.


def _render_prompt(input_: EvidenceSourcerInput) -> tuple[str, str]:
    raw = resolve_active(__file__).path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    body = parts[2] if len(parts) >= 3 else raw
    system_part, user_part = body.split("# User", 1)
    system_part = system_part.replace("# System", "").strip()

    lines = []
    for i, sp in enumerate(input_.retrieved_spans[:10], 1):
        anchor = (
            f"page {sp.anchor_page}" if sp.anchor_kind == "page"
            else (sp.anchor_item or "n/a")
        )
        excerpt = (sp.text or "").strip().replace("\n", " ")[:600]
        lines.append(
            f"[{i}] span_id={sp.span_id}\n"
            f"     source={sp.source}  form={sp.form or '-'}  anchor={anchor}\n"
            f"     score={sp.score:.3f}\n"
            f"     text: {excerpt}"
        )
    spans_block = "\n\n".join(lines) or "(no candidates)"

    library_note = (
        "A library entry already exists for this canonical_id; treat candidate "
        "spans as supporting context unless the entry is stale."
        if input_.library_hit else
        "No library entry exists; the bundle you select will drive a fresh draft."
    )

    user_rendered = (
        user_part.strip()
        .replace("{{canonical_id}}", input_.canonical_id or "(unclassified)")
        .replace("{{question_text}}", input_.raw_question_text.strip())
        .replace("{{library_hit}}", str(input_.library_hit).lower())
        .replace("{{library_note}}", library_note)
        .replace("{{n_spans}}", str(len(input_.retrieved_spans)))
        .replace("{{spans_block}}", spans_block)
    )
    return system_part, user_rendered


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse(text: str) -> dict:
    m = _JSON_RE.search(text)
    if not m:
        return {"selected_span_ids": [], "sufficient": False, "rationale": "no JSON in reply"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"selected_span_ids": [], "sufficient": False, "rationale": "invalid JSON in reply"}


class EvidenceSourcer(Agent):
    name = "EvidenceSourcer"
    version = "1.0.0"

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or AnthropicClient()

    def run(self, agent_input: EvidenceSourcerInput, ctx: RunContext) -> EvidenceSourcerOutput:
        if not agent_input.retrieved_spans:
            ctx.emit(AgentEvent.make(self.name, self.version, "agent.EvidenceSourcer.result", {
                "selected_count": 0, "sufficient": False, "reason": "no candidates",
            }))
            return EvidenceSourcerOutput(
                bundle=[], sufficient=False,
                rationale="No candidate spans were retrieved for this question.",
            )

        system, user = _render_prompt(agent_input)
        req = LLMRequest(tier="tier2_sonnet", system=system, user=user, max_tokens=800)
        ctx.emit(AgentEvent.make(self.name, self.version, "agent.EvidenceSourcer.invoke", {
            "question_id": agent_input.question_id,
            "canonical_id": agent_input.canonical_id,
            "candidate_count": len(agent_input.retrieved_spans),
            "library_hit": agent_input.library_hit,
            "prompt_hash": req.prompt_hash(),
            "model_tier": req.tier,
        }))
        resp = self.llm.complete(req)
        parsed = _parse(resp.text)

        by_id = {s.span_id: s for s in agent_input.retrieved_spans}
        bundle: list[EvidenceSpan] = []
        for sid in (parsed.get("selected_span_ids") or [])[:5]:
            if sid in by_id:
                bundle.append(by_id[sid])
        sufficient = bool(parsed.get("sufficient", False)) and len(bundle) > 0

        out = EvidenceSourcerOutput(
            bundle=bundle,
            sufficient=sufficient,
            rationale=str(parsed.get("rationale", "")).strip()[:600],
        )
        ctx.emit(AgentEvent.make(self.name, self.version, "agent.EvidenceSourcer.result", {
            "selected_count": len(bundle),
            "selected_span_ids": [s.span_id for s in bundle],
            "sufficient": sufficient,
            "response_hash": resp.response_hash(),
            "tokens": {"input": resp.input_tokens, "output": resp.output_tokens,
                       "cache_read": resp.cache_read_tokens},
        }))
        return out
