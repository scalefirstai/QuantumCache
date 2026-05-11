"""PiiScrubber — ddq.md §L06.

Two-pass: (1) deterministic regex for SSN / account-number patterns;
(2) Claude Haiku for contextual leakage (internal client names, employee
names, ticket IDs). Presidio integration is M1 work; the regex pass here
is the dev backstop.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from core.ports.agent import Agent, AgentEvent, RunContext
from packages.llm_sdk import AnthropicClient, LLMClient, LLMRequest
from packages.schemas.agents import PiiFinding, PiiScrubberInput, PiiScrubberOutput


PROMPT_PATH = Path(__file__).parent / "prompts" / "v1.0.0.md"

SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
ACCT_RE = re.compile(r"\b(?:account|acct)[ :#-]*\d{6,}\b", flags=re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
TICKET_RE = re.compile(r"\b(JIRA|SNOW|INC|TKT)-\d{3,}\b", flags=re.IGNORECASE)
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _deterministic_scan(text: str) -> tuple[str, list[PiiFinding]]:
    findings: list[PiiFinding] = []
    cleaned = text
    for label, regex, sev in (
        ("SSN", SSN_RE, "halt"),
        ("ACCOUNT_NUMBER", ACCT_RE, "halt"),
        ("EMAIL", EMAIL_RE, "warn"),
        ("TICKET", TICKET_RE, "warn"),
    ):
        for m in regex.finditer(cleaned):
            findings.append(PiiFinding(kind=label, span=m.group(0)[:80], severity=sev))
        cleaned = regex.sub(f"[REDACTED:{label}]", cleaned)
    return cleaned, findings


def _render_prompt(text: str) -> tuple[str, str]:
    raw = PROMPT_PATH.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    body = parts[2] if len(parts) >= 3 else raw
    system_part, user_part = body.split("# User", 1)
    system_part = system_part.replace("# System", "").strip()
    user_rendered = user_part.strip().replace("{{draft_text}}", text.strip())
    return system_part, user_rendered


def _parse(text: str) -> dict:
    m = _JSON_RE.search(text)
    if not m:
        return {"clean_text": "", "findings": [], "halt": False}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"clean_text": "", "findings": [], "halt": False}


class PiiScrubber(Agent):
    name = "PiiScrubber"
    version = "1.0.0"

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or AnthropicClient()

    def run(self, agent_input: PiiScrubberInput, ctx: RunContext) -> PiiScrubberOutput:
        # 1. Deterministic pass.
        regex_clean, regex_findings = _deterministic_scan(agent_input.draft_text)

        # 2. Contextual LLM pass on the already-cleaned text.
        system, user = _render_prompt(regex_clean)
        req = LLMRequest(tier="tier3_haiku", system=system, user=user, max_tokens=600)
        ctx.emit(AgentEvent.make(self.name, self.version, "agent.PiiScrubber.invoke", {
            "regex_findings": len(regex_findings),
            "input_chars": len(agent_input.draft_text),
            "prompt_hash": req.prompt_hash(),
        }))
        resp = self.llm.complete(req)
        parsed = _parse(resp.text)

        llm_findings: list[PiiFinding] = []
        for f in (parsed.get("findings") or []):
            try:
                llm_findings.append(PiiFinding(
                    kind=str(f.get("kind", "OTHER"))[:32],
                    span=str(f.get("span", ""))[:120],
                    severity=str(f.get("severity", "warn")),
                ))
            except Exception:
                continue
        all_findings = regex_findings + llm_findings
        clean_text = (parsed.get("clean_text") or regex_clean).strip()
        halt = bool(parsed.get("halt", False)) or any(f.severity == "halt" for f in all_findings)

        out = PiiScrubberOutput(clean_text=clean_text, findings=all_findings, halt=halt)
        ctx.emit(AgentEvent.make(self.name, self.version, "agent.PiiScrubber.result", {
            "findings_total": len(all_findings),
            "regex_findings": len(regex_findings),
            "llm_findings": len(llm_findings),
            "halt": halt,
            "response_hash": resp.response_hash(),
            "tokens": {"input": resp.input_tokens, "output": resp.output_tokens,
                       "cache_read": resp.cache_read_tokens},
        }))
        return out
