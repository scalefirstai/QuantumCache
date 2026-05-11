"""ConsistencyChecker — ddq.md §L06.

Sonnet-tier. Compares the new draft against recent shipped responses for the
same canonical_id (sourced from DuckDB.response_register in M1+; from a
caller-supplied list here).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from core.ports.agent import Agent, AgentEvent, RunContext
from packages.llm_sdk import AnthropicClient, LLMClient, LLMRequest
from packages.schemas.agents import (
    ConsistencyCheckerInput, ConsistencyCheckerOutput,
)


PROMPT_PATH = Path(__file__).parent / "prompts" / "v1.0.0.md"
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _render_prompt(input_: ConsistencyCheckerInput) -> tuple[str, str]:
    raw = PROMPT_PATH.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    body = parts[2] if len(parts) >= 3 else raw
    system_part, user_part = body.split("# User", 1)
    system_part = system_part.replace("# System", "").strip()

    lines = []
    for p in input_.prior_responses[:5]:
        lines.append(
            f"run_id={p.run_id}  sealed_at={p.sealed_at}\n"
            f"  text: {p.response_text.strip()[:800]}"
        )
    prior_block = "\n\n".join(lines) or "(no prior responses for this canonical_id)"

    user_rendered = (
        user_part.strip()
        .replace("{{canonical_id}}", input_.canonical_id or "(unclassified)")
        .replace("{{draft_text}}", input_.draft_text.strip())
        .replace("{{prior_block}}", prior_block)
    )
    return system_part, user_rendered


def _parse(text: str) -> dict:
    m = _JSON_RE.search(text)
    if not m:
        return {"consistent": False, "drift_detected": True,
                "diff_summary": None, "notes": "no JSON in reply"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"consistent": False, "drift_detected": True,
                "diff_summary": None, "notes": "invalid JSON in reply"}


class ConsistencyChecker(Agent):
    name = "ConsistencyChecker"
    version = "1.0.0"

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or AnthropicClient()

    def run(self, agent_input: ConsistencyCheckerInput, ctx: RunContext) -> ConsistencyCheckerOutput:
        if not agent_input.prior_responses:
            ctx.emit(AgentEvent.make(self.name, self.version, "agent.ConsistencyChecker.result", {
                "consistent": True, "drift_detected": False,
                "reason": "no prior responses for this canonical_id",
            }))
            return ConsistencyCheckerOutput(
                consistent=True, drift_detected=False,
                notes="No prior shipped responses for this canonical_id.",
                diff_summary=None,
            )

        system, user = _render_prompt(agent_input)
        req = LLMRequest(tier="tier2_sonnet", system=system, user=user, max_tokens=800)
        ctx.emit(AgentEvent.make(self.name, self.version, "agent.ConsistencyChecker.invoke", {
            "canonical_id": agent_input.canonical_id,
            "prior_count": len(agent_input.prior_responses),
            "prompt_hash": req.prompt_hash(),
        }))
        resp = self.llm.complete(req)
        parsed = _parse(resp.text)

        consistent = bool(parsed.get("consistent", False))
        drift = bool(parsed.get("drift_detected", not consistent))

        out = ConsistencyCheckerOutput(
            consistent=consistent and not drift,
            drift_detected=drift,
            notes=str(parsed.get("notes", "")).strip()[:400],
            diff_summary=(parsed.get("diff_summary") or None),
        )
        ctx.emit(AgentEvent.make(self.name, self.version, "agent.ConsistencyChecker.result", {
            "consistent": out.consistent, "drift_detected": out.drift_detected,
            "response_hash": resp.response_hash(),
            "tokens": {"input": resp.input_tokens, "output": resp.output_tokens,
                       "cache_read": resp.cache_read_tokens},
        }))
        return out
