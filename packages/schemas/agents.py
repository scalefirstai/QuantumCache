"""Per-agent input/output schemas — ddq.md §L06.

All Pydantic v2; JSON-serializable so the audit journal can hash + replay.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── shared types ──────────────────────────────────────────────────
class EvidenceSpan(BaseModel):
    span_id: str
    doc_id: Optional[str] = None
    doc_hash: Optional[str] = None
    span_hash: Optional[str] = None
    source: Optional[str] = None
    form: Optional[str] = None
    anchor_kind: Optional[str] = None
    anchor_page: Optional[int] = None
    anchor_item: Optional[str] = None
    text: str = ""
    score: float = 0.0


class CitationRef(BaseModel):
    span_id: str
    doc_hash: str
    span_hash: str
    excerpt: str = ""                    # quoted text from span


# ── QuestionMapper ────────────────────────────────────────────────
class QuestionMapperInput(BaseModel):
    question_id: str                     # incoming framework Q id, e.g. "AFME-7.1"
    framework: str
    raw_question_text: str
    candidate_canonicals: list[dict] = Field(default_factory=list)


class QuestionMapperOutput(BaseModel):
    canonical_id: Optional[str]          # null = unclassified → SME
    confidence: float                    # 0..1
    rationale: str
    routed_to_sme: bool = False


# ── EvidenceSourcer ───────────────────────────────────────────────
class EvidenceSourcerInput(BaseModel):
    question_id: str
    raw_question_text: str
    canonical_id: Optional[str]
    library_hit: bool
    library_entry: Optional[dict] = None
    retrieved_spans: list[EvidenceSpan] = Field(default_factory=list)


class EvidenceSourcerOutput(BaseModel):
    bundle: list[EvidenceSpan]           # curated subset, ordered by relevance
    rationale: str
    sufficient: bool                     # if False, escalate to SME with no draft


# ── DraftComposer ────────────────────────────────────────────────
class DraftComposerInput(BaseModel):
    question_id: str
    raw_question_text: str
    canonical_id: Optional[str]
    tier: Literal["tier1_opus", "tier2_sonnet", "tier3_haiku"] = "tier2_sonnet"
    evidence_bundle: list[EvidenceSpan]
    library_entry_text: Optional[str] = None     # if library hit, prefer this


class DraftComposerOutput(BaseModel):
    draft_text: str
    citations: list[CitationRef]
    tier_used: str
    used_library_entry: bool


# ── CitationVerifier ─────────────────────────────────────────────
class CitationVerifierInput(BaseModel):
    draft_text: str
    citations: list[CitationRef]
    span_lookup: dict[str, str] = Field(default_factory=dict)  # span_hash → canonical text


class CitationCheckResult(BaseModel):
    span_hash: str
    resolved: bool
    excerpt_matches_span: bool
    reason: Optional[str] = None


class CitationVerifierOutput(BaseModel):
    all_pass: bool
    results: list[CitationCheckResult]
    summary: str


# ── ConsistencyChecker ───────────────────────────────────────────
class PriorResponse(BaseModel):
    run_id: str
    sealed_at: str
    canonical_id: str
    response_text: str


class ConsistencyCheckerInput(BaseModel):
    canonical_id: Optional[str]
    draft_text: str
    prior_responses: list[PriorResponse] = Field(default_factory=list)


class ConsistencyCheckerOutput(BaseModel):
    consistent: bool
    drift_detected: bool
    notes: str
    diff_summary: Optional[str] = None


# ── PiiScrubber ───────────────────────────────────────────────────
class PiiScrubberInput(BaseModel):
    draft_text: str


class PiiFinding(BaseModel):
    kind: str                            # "SSN", "ACCOUNT_NUMBER", "EMAIL", "INTERNAL_REF", etc.
    span: str                            # excerpt, redacted
    severity: Literal["info", "warn", "halt"] = "warn"


class PiiScrubberOutput(BaseModel):
    clean_text: str                      # text with redactions applied
    findings: list[PiiFinding]
    halt: bool                           # any halt-severity finding


# ── FreshnessAuditor (rule-based) ─────────────────────────────────
class FreshnessAuditorInput(BaseModel):
    library_entry: Optional[dict] = None
    evidence_bundle: list[EvidenceSpan] = Field(default_factory=list)
    today: str                           # ISO date


class FreshnessAuditorOutput(BaseModel):
    stale: bool
    reasons: list[str]
    oldest_evidence_date: Optional[str] = None


# ── ApprovalRouter (rule-based) ──────────────────────────────────
class ApprovalRouterInput(BaseModel):
    canonical_id: Optional[str]
    classify_confidence: float
    validate_verdict: Literal["pass", "halt", "escalate"]
    pii_halt: bool
    freshness_stale: bool
    consistency_drift: bool


class ApprovalRouterOutput(BaseModel):
    route: Literal["auto_approve", "sme_queue", "legal_review", "halt"]
    queue: Optional[str]                 # "infosec" | "ops" | "regulatory" | "esg" | "cyber" | "legal"
    tier: Literal["tier1", "tier2", "tier3"]
    rationale: str
