"""QuestionMapper — ddq.md §L06.

Haiku-tier classifier. Takes a candidate shortlist from Qdrant (built by the
orchestrator via reverse-lookup over framework spans), asks Claude to pick the
single best canonical_id or refuse, and emits a calibrated confidence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from core.ports.agent import Agent, AgentEvent, RunContext
from packages.llm_sdk import AnthropicClient, LLMClient, LLMRequest
from packages.prompts import resolve_active
from packages.schemas.agents import QuestionMapperInput, QuestionMapperOutput


SME_CONFIDENCE_THRESHOLD = 0.70


def _render_prompt(input_: QuestionMapperInput) -> tuple[str, str]:
    raw = resolve_active(__file__).path.read_text(encoding="utf-8")
    # Split off YAML frontmatter.
    parts = raw.split("---", 2)
    body = parts[2] if len(parts) >= 3 else raw
    system_part, user_part = body.split("# User", 1)
    system_part = system_part.replace("# System", "").strip()

    cand_lines = []
    for c in input_.candidate_canonicals[:10]:
        cid = c.get("canonical_id", "")
        ref = f"{c.get('framework','')}/{c.get('question_ref','')}"
        score = c.get("dense_score", 0.0)
        cand_lines.append(f"- {cid}  (matched via {ref}, similarity {score:.3f})")
    candidate_block = "\n".join(cand_lines) or "- (none)"

    user_rendered = (
        user_part.strip()
        .replace("{{framework}}", input_.framework)
        .replace("{{question_id}}", input_.question_id)
        .replace("{{question_text}}", input_.raw_question_text.strip())
        .replace("{{n_candidates}}", str(len(input_.candidate_canonicals)))
        .replace("{{candidate_block}}", candidate_block)
    )
    return system_part, user_rendered


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json(text: str) -> dict:
    m = _JSON_RE.search(text)
    if not m:
        return {"canonical_id": None, "confidence": 0.0, "rationale": "no JSON in model reply"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"canonical_id": None, "confidence": 0.0, "rationale": "invalid JSON in model reply"}


class QuestionMapper(Agent):
    name = "QuestionMapper"
    version = "1.0.0"

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or AnthropicClient()

    def run(self, agent_input: QuestionMapperInput, ctx: RunContext) -> QuestionMapperOutput:
        system, user = _render_prompt(agent_input)
        req = LLMRequest(tier="tier3_haiku", system=system, user=user, max_tokens=256)
        ctx.emit(AgentEvent.make(self.name, self.version, "agent.QuestionMapper.invoke", {
            "question_id": agent_input.question_id,
            "framework": agent_input.framework,
            "candidate_count": len(agent_input.candidate_canonicals),
            "prompt_hash": req.prompt_hash(),
            "model_tier": req.tier,
        }))
        resp = self.llm.complete(req)
        parsed = _parse_json(resp.text)

        canonical_id = parsed.get("canonical_id")
        candidate_ids = {c.get("canonical_id") for c in agent_input.candidate_canonicals}
        if canonical_id and canonical_id not in candidate_ids:
            # Model invented an ID outside the shortlist → reject.
            canonical_id = None

        confidence = float(parsed.get("confidence") or 0.0)
        confidence = max(0.0, min(1.0, confidence))
        routed_to_sme = (canonical_id is None) or (confidence < SME_CONFIDENCE_THRESHOLD)

        out = QuestionMapperOutput(
            canonical_id=canonical_id,
            confidence=confidence,
            rationale=str(parsed.get("rationale", "")).strip()[:300],
            routed_to_sme=routed_to_sme,
        )
        ctx.emit(AgentEvent.make(self.name, self.version, "agent.QuestionMapper.result", {
            "canonical_id": out.canonical_id,
            "confidence": out.confidence,
            "routed_to_sme": out.routed_to_sme,
            "response_hash": resp.response_hash(),
            "tokens": {
                "input": resp.input_tokens, "output": resp.output_tokens,
                "cache_read": resp.cache_read_tokens,
            },
        }))
        return out
