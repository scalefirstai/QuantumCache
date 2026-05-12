"""
Skills registry + the legacy /api/v1/skills/{id} detail endpoint.

  GET /api/v1/skills                → SkillSummary[]   (new catalog)
  GET /api/v1/skills/{id}           → SkillDetail/Summary (legacy 'retrieval-hybrid' returns rich)

The summary catalog mirrors the toolset declared in
infra/adapters/fs_prompts.LLM_AGENTS so each skill knows which agents
default to using it.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from infra.adapters.fs_prompts import LLM_AGENTS, RULE_AGENTS

from ..deps import Container, container

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


SKILLS: dict[str, dict] = {
    "retrieval.hybrid":   {"name": "Retrieval.hybrid",   "category": "retrieval", "ownedBy": "L03",
                           "description": "BM25 + dense + RRF over the BNY corpus.",
                           "signature": "hybrid(question, k=10) → list[EvidenceSpan]"},
    "library.lookup":     {"name": "Library.lookup",     "category": "library",   "ownedBy": "L04",
                           "description": "Mongo-backed lookup of approved library entries.",
                           "signature": "lookup(LibraryKey) → LibraryEntry | None"},
    "taxonomy.classify":  {"name": "Taxonomy.classify",  "category": "taxonomy",  "ownedBy": "L05",
                           "description": "Maps question + candidates to canonical_id + confidence.",
                           "signature": "classify(question, candidates) → (canonical_id, confidence)"},
    "embedding.search":   {"name": "Embedding.search",   "category": "retrieval", "ownedBy": "L03",
                           "description": "Dense vector search over Qdrant.",
                           "signature": "search(text, k) → list[ScoredPoint]"},
    "embedding.similarity": {"name": "Embedding.similarity", "category": "retrieval", "ownedBy": "L03",
                             "description": "Cosine similarity between two embeddings.",
                             "signature": "similarity(a, b) → float"},
    "llm.complete":       {"name": "LLM.complete",       "category": "llm",        "ownedBy": "L06",
                           "description": "Single Anthropic completion against the configured tier.",
                           "signature": "complete(system, user, model) → CompletionResult"},
    "prompt.registry":    {"name": "Prompt.registry",    "category": "llm",        "ownedBy": "L06",
                           "description": "Resolves the active prompt version for a given agent.",
                           "signature": "resolve(agent_id) → PromptDocument"},
    "corpus.fetch_span":  {"name": "Corpus.fetch_span",  "category": "retrieval",  "ownedBy": "L02",
                           "description": "Fetch a specific span by hash from OpenSearch.",
                           "signature": "fetch(span_hash) → str | None"},
    "hash.verify":        {"name": "Hash.verify",        "category": "audit",      "ownedBy": "L02",
                           "description": "Re-hashes a span and compares against the stored span_hash.",
                           "signature": "verify(span_text, span_hash) → bool"},
    "duckdb.query":       {"name": "DuckDB.query",       "category": "analytics",  "ownedBy": "L05",
                           "description": "Time-windowed SQL over the response_register parquet shards.",
                           "signature": "query(sql) → list[Row]"},
    "presidio.analyze":   {"name": "Presidio.analyze",   "category": "pii",        "ownedBy": "L08",
                           "description": "Presidio analyzer pass; returns recognized PII entities.",
                           "signature": "analyze(text) → list[AnalyzerResult]"},
    "regex.recognizer":   {"name": "RegexRecognizer",    "category": "pii",        "ownedBy": "L08",
                           "description": "Custom regex recognizers for BNY internal-reference patterns.",
                           "signature": "scan(text) → list[Finding]"},
    "library.expiry":     {"name": "Library.expiry",     "category": "library",    "ownedBy": "L04",
                           "description": "Returns the configured expiry rule for a library entry's tier.",
                           "signature": "expiry(entry) → timedelta"},
    "corpus.freshness":   {"name": "Corpus.freshness",   "category": "library",    "ownedBy": "L02",
                           "description": "Latest doc_date for a given source.",
                           "signature": "freshness(source) → date"},
    "opa.evaluate":       {"name": "OPA.evaluate",       "category": "policy",     "ownedBy": "L08",
                           "description": "Evaluate a Rego policy bundle against an input document.",
                           "signature": "evaluate(policy, input) → Decision"},
    "queue.enqueue":      {"name": "Queue.enqueue",      "category": "approval",   "ownedBy": "L08",
                           "description": "Enqueue a run for SME review on the right domain queue.",
                           "signature": "enqueue(run_id, queue, tier) → None"},
}


def _used_by(skill_id: str) -> list[str]:
    out = []
    for meta in {**LLM_AGENTS, **RULE_AGENTS}.values():
        if skill_id in (meta.get("default_tools") or []):
            out.append(meta["name"])
    return out


def _summary(skill_id: str, s: dict) -> dict:
    return {
        "id":          skill_id,
        "name":        s["name"],
        "category":    s["category"],
        "ownedBy":     s["ownedBy"],
        "description": s["description"],
        "signature":   s["signature"],
        "usedBy":      _used_by(skill_id),
    }


def _require_manifest(c: Container, name: str) -> dict:
    data = c.manifests.get(name)
    if data is None:
        raise HTTPException(
            status_code=503,
            detail=f"Required manifest '{name}' is missing — run the bootstrap pipeline.",
        )
    return data


@router.get("")
def list_skills() -> list[dict]:
    return [_summary(sid, s) for sid, s in SKILLS.items()]


@router.get("/{skill_id}")
def get_skill(skill_id: str) -> dict:
    # Legacy: the existing UI route /skills/retrieval-hybrid expects the
    # rich SkillDetail shape backed by bootstrap reports.
    if skill_id == "retrieval-hybrid":
        c = container()
        eval_report = _require_manifest(c, "eval-v0-baseline")
        hybrid = _require_manifest(c, "hybrid-smoke")
        os_report = _require_manifest(c, "opensearch-index")
        qdrant_report = _require_manifest(c, "qdrant-index")
        return c.builders.build_skill(eval_report, hybrid, os_report, qdrant_report)
    s = SKILLS.get(skill_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")
    return _summary(skill_id, s)
