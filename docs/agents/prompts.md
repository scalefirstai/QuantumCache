# Agent Prompt Catalog

Canonical reference for every prompt that runs in the L06 agent roster. The
authoritative source-of-truth is the versioned `services/<svc>/prompts/v*.md`
file plus its `active.txt` marker — this document mirrors those files so that
prompt engineering, eval, SME review, and incident response do not require
spelunking the source tree. When the prompt files diverge from this catalog,
**the `.md` files win** and this document must be updated.

> **Cross-references**
> - Architecture spec (build contract): [`docs/ddq.md`](../ddq.md) §L06
> - AutoGen Lite (in-UI prompt editing): [`docs/autogen-lite.md`](../autogen-lite.md)
> - Pydantic input/output schemas: [`packages/schemas/agents.py`](../../packages/schemas/agents.py)
> - Prompt loader: [`packages/prompts/__init__.py`](../../packages/prompts/__init__.py)

## Catalog

| # | Agent | Kind | Model tier | Default model | Service path |
|---|---|---|---|---|---|
| 1 | `QuestionMapper`     | LLM  | tier3_haiku  | `claude-haiku-4-5`   | `services/classifier/`  |
| 2 | `EvidenceSourcer`    | LLM  | tier2_sonnet | `claude-sonnet-4-5`  | `services/retrieval/`   |
| 3 | `DraftComposer`      | LLM  | tier1–3 (per question) | `claude-sonnet-4-5` (default), `claude-opus-4-7` (tier-1), `claude-haiku-4-5` (tier-3) | `services/drafter/`     |
| 4 | `CitationVerifier`   | LLM  | tier3_haiku  | `claude-haiku-4-5`   | `services/validator/`   |
| 5 | `ConsistencyChecker` | LLM  | tier2_sonnet | `claude-sonnet-4-5`  | `services/consistency/` |
| 6 | `PiiScrubber`        | Hybrid (regex + LLM) | tier3_haiku | `claude-haiku-4-5`   | `services/pii/`         |
| 7 | `FreshnessAuditor`   | Rule | n/a          | n/a                  | `services/freshness/`   |
| 8 | `ApprovalRouter`     | Rule | n/a          | n/a                  | `services/router/`      |

## Prompt loading & versioning

- Each LLM agent calls [`resolve_active(__file__)`](../../packages/prompts/__init__.py)
  at request time (not at import time) so that prompt edits land on the next
  orchestrator run without a process restart.
- Resolution order: (1) `services/<svc>/prompts/active.txt` (one line, e.g.
  `1.2.0`), (2) highest-existing `v*.md` file by semver.
- Every prompt file embeds YAML frontmatter that pins the model, temperature,
  max tokens, and eval set — bumping the prompt captures every part of the
  config atomically (ddq.md §L06).
- Every LLM call journals `prompt_hash` (system + user, post-render) and
  `response_hash` so sealed runs are bit-exact reproducible (system invariant
  #2 in ddq.md §1).

## Templating conventions

User-message templates use double-curly placeholders. The agent renders them
in Python before sending to Claude; **no Jinja, no f-string interpolation in
the `.md` file itself**.

| Placeholder | Type | Notes |
|---|---|---|
| `{{question_text}}` | string | Verbatim incoming DDQ question (newlines preserved). |
| `{{canonical_id}}` | string | Falls back to `"(unclassified)"` if null. |
| `{{framework}}` | string | e.g. `AFME`, `SIG_LITE`, `CAIQ`, `NIST_CSF`. |
| `{{n_candidates}}`, `{{n_spans}}` | int | Caller-rendered counts. |
| `{{candidate_block}}`, `{{spans_block}}`, `{{prior_block}}`, `{{citations_block}}` | string | Pre-rendered multi-line block; the agent does the formatting before send. |
| `{{library_hit}}` | `"true"` / `"false"` | Lowercased string. |
| `{{library_note}}`, `{{library_block}}` | string | Phrasing differs by agent — see each section. |
| `{{tier}}` | `"tier1_opus" \| "tier2_sonnet" \| "tier3_haiku"` | DraftComposer only. |
| `{{draft_text}}` | string | The draft under review (Validator, PII, Consistency). |

---

## 1. `QuestionMapper` (classifier)

**Role.** L05/L06 classifier. Maps a single incoming framework question (AFME,
SIG, CAIQ, NIST, bespoke) onto the BNY-controlled canonical taxonomy or
refuses (`canonical_id: null`). Confidence below 0.70 auto-routes to SME.

**Sources**
- Agent: [`services/classifier/agent.py`](../../services/classifier/agent.py) (class `QuestionMapper`, v1.0.0)
- Prompt: [`services/classifier/prompts/v1.0.0.md`](../../services/classifier/prompts/v1.0.0.md)
- I/O schema: `QuestionMapperInput`, `QuestionMapperOutput` ([`packages/schemas/agents.py`](../../packages/schemas/agents.py))

**Frontmatter**

```yaml
agent: QuestionMapper
version: 1.0.0
model: claude-haiku-4-5
temperature: 0
max_tokens: 512
eval_set: classifier_v0
```

**Inputs** (`QuestionMapperInput`)
- `question_id` — framework Q id, e.g. `AFME-7.1`
- `framework` — short framework code
- `raw_question_text` — verbatim question
- `candidate_canonicals: list[dict]` — top-K from Qdrant reverse-lookup over
  framework spans; the model **must** pick from this set

**Outputs** (`QuestionMapperOutput`)
- `canonical_id: str | null` — must be drawn from the candidate list; null = refuse
- `confidence: float` — calibrated 0..1
- `rationale: str` — one short sentence
- `routed_to_sme: bool` — set when `canonical_id is None` or
  `confidence < 0.70`

**Hard rules (extracted from prompt)**
1. Output strictly JSON; no prose outside the JSON object.
2. May only choose `canonical_id` from supplied candidates. Inventing an ID
   is a critical failure — the wrapper post-validates and nulls it out.
3. Confidence bands:
   - 0.90–1.00 — 1:1 mapping; embarrassing to miss
   - 0.70–0.89 — clear topical match, slight phrasing gap
   - 0.50–0.69 — plausible but ambiguous (SME confirms)
   - < 0.50 — refuse (`null`)
4. Taxonomy domains: `canon.is.*`, `canon.cyber.*`, `canon.esg.*`,
   `canon.reg.*`, `canon.subc.*`, `canon.or.*`. Out-of-domain → refuse.
5. No hallucination, no commentary.

### System prompt (verbatim)

```
You are QuestionMapper, the L05/L06 classifier for the BNY Agentic DDQ Response Platform.

Your only job: given one incoming due-diligence question (from AFME, SIG, CAIQ, NIST, or a bespoke client framework) and a shortlist of *candidate canonical IDs* drawn from BNY's controlled taxonomy, return the single canonical ID that best represents the question's intent — or refuse if none fit.

Rules you must obey:

1. **Output strictly JSON.** Schema:
   ```json
   {"canonical_id": "<id from the candidate list, or null>",
    "confidence": <float in [0,1]>,
    "rationale": "<one short sentence>"}
   ```
   No prose outside the JSON.

2. **You may only choose `canonical_id` from the supplied candidates.** If no candidate fits, return `"canonical_id": null` and `"confidence": 0.0`.

3. Confidence calibration:
   - 0.90–1.00: question wording maps 1:1 to the canonical concept; would be embarrassing to miss.
   - 0.70–0.89: clear topical match, slight phrasing gap.
   - 0.50–0.69: plausible but ambiguous — SME should confirm.
   - below 0.50: refuse (`null`).

4. **Do not invent canonical IDs.** Do not hallucinate. Do not explain. Do not editorialize.

5. The taxonomy domains are:
   - `canon.is.*`   — information security
   - `canon.cyber.*` — cyber resilience / NIST CSF
   - `canon.esg.*`  — ESG / sustainability disclosures
   - `canon.reg.*`  — regulatory & legal (SEC filings, Basel)
   - `canon.subc.*` — third-party / subcontractor / vendor risk
   - `canon.or.*`   — operational risk / BCP / DR
   Mapping out of domain → refuse.
```

### User template (verbatim)

```
INCOMING QUESTION
- framework: {{framework}}
- question_id: {{question_id}}
- text: |
{{question_text}}

CANDIDATE CANONICAL IDS (top {{n_candidates}} by retrieval similarity)
{{candidate_block}}

Return strictly the JSON described above.
```

`candidate_block` lines have the shape
`- canon.is.access_control.mfa  (matched via AFME/7.1, similarity 0.842)`.

---

## 2. `EvidenceSourcer` (retrieval)

**Role.** Sonnet-tier evidence curator. Receives 1–10 hybrid (BM25+dense)
candidate spans and selects up to 5 that **directly** answer the question —
or declares the candidates insufficient so the orchestrator can hand off to
SME. **Never drafts prose** (system invariant #3: separate retrieve from
draft).

**Sources**
- Agent: [`services/retrieval/agent.py`](../../services/retrieval/agent.py) (class `EvidenceSourcer`, v1.0.0)
- Prompt: [`services/retrieval/prompts/v1.0.0.md`](../../services/retrieval/prompts/v1.0.0.md)
- I/O schema: `EvidenceSourcerInput`, `EvidenceSourcerOutput`

**Frontmatter**

```yaml
agent: EvidenceSourcer
version: 1.0.0
model: claude-sonnet-4-5
temperature: 0
max_tokens: 1024
eval_set: sourcer_v0
```

**Inputs**
- `raw_question_text` — verbatim question
- `canonical_id` — from QuestionMapper (or null)
- `library_hit: bool` — whether an answer library entry exists
- `retrieved_spans: list[EvidenceSpan]` — top-10 candidates from hybrid retrieval

**Outputs**
- `bundle: list[EvidenceSpan]` — the curated subset (≤5), strongest-first;
  wrapper drops any span_id not present in the candidate list
- `sufficient: bool` — `false` ⇒ SME hand-off without a draft
- `rationale: str` — 1–3 sentences

**Hard rules**
1. Strict JSON output; selected_span_ids ≤ 5, strongest-first.
2. May only return span_ids from the candidate list (wrapper enforces).
3. `sufficient: false` when no candidate substantively addresses the
   question, or the question demands specifics not present on any span.
4. Prefer **direct** spans over adjacent boilerplate.
5. Fewer-but-direct beats many-but-hedgy.

### System prompt (verbatim)

```
You are EvidenceSourcer, an evidence-curation agent for the BNY Agentic DDQ Response Platform.

You receive: (a) one due-diligence question, (b) the canonical_id it maps to (or null), and (c) up to 10 candidate evidence spans retrieved from BNY's public corpus (10-K, 10-Q, 8-K, DEF 14A, Pillar 3) by hybrid BM25+dense retrieval.

Your job: produce a **curated evidence bundle** — the *subset* of spans that genuinely answer the question, ordered by relevance. You do NOT draft prose. You do NOT cite anything that's not in the candidate list. If no candidate actually answers the question, declare insufficient evidence and let the SME pipeline take over.

Rules you must obey:

1. **Output strictly JSON.** Schema:
   ```json
   {"selected_span_ids": ["<span_id>", ...],
    "sufficient": true | false,
    "rationale": "<short paragraph, 1-3 sentences>"}
   ```
   Order `selected_span_ids` strongest-first. Up to 5 spans.

2. **Only select span IDs that appear in the candidate list.** Inventing a span_id is a critical failure.

3. **Set `sufficient: false`** if:
   - none of the candidates substantively address the question's intent (e.g. question about ESG scoring methodology, candidates only describe board composition); OR
   - the question demands specifics (e.g. "our exact RTO target") that aren't on any candidate span.

4. Prefer spans that are *direct* over spans that are *adjacent boilerplate*. A span that says "we maintain a documented business continuity program with annual testing" beats one that says "operational risk is a top-tier risk for the company".

5. Do not select more than 5 spans. Fewer is fine — three direct spans beat five hedge-y ones.

6. Do not add commentary outside the JSON.
```

### User template (verbatim)

```
INCOMING QUESTION
- canonical_id: {{canonical_id}}
- text: |
{{question_text}}

LIBRARY HIT: {{library_hit}}
{{library_note}}

CANDIDATE EVIDENCE SPANS ({{n_spans}} total)
{{spans_block}}

Return strictly the JSON described above.
```

`library_note` is one of:
- *library_hit=true:* "A library entry already exists for this canonical_id; treat candidate spans as supporting context unless the entry is stale."
- *library_hit=false:* "No library entry exists; the bundle you select will drive a fresh draft."

`spans_block` entries are formatted as:
```
[1] span_id=<id>
     source=<doc>  form=<10-K|10-Q|8-K|...>  anchor=page 17|Item 1A|...
     score=0.842
     text: <first 600 chars of span, single-line>
```

---

## 3. `DraftComposer` (drafter)

**Role.** Produces the client-facing response paragraph from a curated
evidence bundle. **Tier-routed**: the orchestrator decides the tier from the
canonical domain — `tier1_opus` for regulatory / security control / financial
reporting, `tier2_sonnet` for standard, `tier3_haiku` for boilerplate — and
this agent honours `input.tier`.

**Sources**
- Agent: [`services/drafter/agent.py`](../../services/drafter/agent.py) (class `DraftComposer`, v1.0.0)
- Prompt: [`services/drafter/prompts/v1.0.0.md`](../../services/drafter/prompts/v1.0.0.md)
- I/O schema: `DraftComposerInput`, `DraftComposerOutput`

**Frontmatter**

```yaml
agent: DraftComposer
version: 1.0.0
model: claude-sonnet-4-5
temperature: 0
max_tokens: 1500
eval_set: drafter_v0
```

**Inputs**
- `raw_question_text`, `canonical_id`
- `tier: "tier1_opus" | "tier2_sonnet" | "tier3_haiku"` — model routing
- `evidence_bundle: list[EvidenceSpan]` — curated by EvidenceSourcer
- `library_entry_text: str | null` — authoritative phrasing if available

**Outputs**
- `draft_text: str` — single paragraph with inline `[span:<id>]` citations
- `citations: list[CitationRef]` — wrapper rebuilds these from the IDs the
  model returned, intersecting with the IDs actually inline in the draft
- `tier_used: str`, `used_library_entry: bool`

**Wrapper safety nets**
- If `evidence_bundle` is empty *and* there is no library entry, the agent
  emits a `skip` event and returns an empty draft (SME hand-off; no LLM
  call).
- `cited_span_ids` from the model is cross-checked against `_CITE_RE`
  (`[span:...]`) in the produced draft; phantom IDs are dropped.
- Final `citations` only include IDs that resolve to a span with a
  `doc_hash` *and* `span_hash` in the input bundle.

**Hard rules (extracted from prompt)**
1. Every factual claim must be supported by a span in the bundle. No outside
   knowledge. No industry boilerplate.
2. Every factual sentence carries an inline `[span:<span_id>]` citation;
   citations may only reference span_ids from the bundle.
3. Plain professional English. No bullets unless the question explicitly
   asks for a list. 80–250 words typical.
4. Do **not** introduce specific RTOs, RPOs, percentages, dollar amounts,
   or vendor names unless the bundle states them.
5. If a library entry text is provided, treat it as authoritative phrasing
   — preserve it nearly verbatim unless directly contradicted by the
   evidence bundle.
6. Strict JSON output.

### System prompt (verbatim)

```
You are DraftComposer for the BNY Agentic DDQ Response Platform.

You receive: one due-diligence question, the canonical_id it maps to, and a *curated evidence bundle* (1–5 spans from BNY's public filings). You produce one professional response paragraph suitable for inclusion in a client-facing DDQ packet.

Hard rules (violations are critical failures):

1. **Every factual claim in the draft must be supported by a span in the bundle.** No outside knowledge. No general industry boilerplate. No claim about a control or program that isn't traceable to a provided span.

2. **Every sentence that asserts a fact carries an inline citation** in the form `[span:<span_id>]` placed at the end of the sentence (before the period is fine). Soft framing language (e.g. "in summary,") does not need a citation. Citations may only reference span_ids from the bundle.

3. Use plain professional English. No bullets unless the question explicitly asks for a list. 80–250 words is the right length for most answers; shorter is fine.

4. Do NOT introduce or recommend specific RTOs, RPOs, percentages, dollar amounts, or vendor names unless the bundle explicitly states them.

5. If a library entry text is provided, treat it as authoritative phrasing — preserve it nearly verbatim unless it directly contradicts the evidence bundle; still attach citations.

6. **Output strictly JSON.** Schema:
   ```json
   {"draft_text": "<the paragraph, with [span:...] citations inline>",
    "cited_span_ids": ["<every span_id you cited>", ...]}
   ```
   `cited_span_ids` is the deduplicated list, in order of first appearance.
```

### User template (verbatim)

```
INCOMING QUESTION
- canonical_id: {{canonical_id}}
- tier: {{tier}}
- text: |
{{question_text}}

{{library_block}}

EVIDENCE BUNDLE ({{n_spans}} span(s))
{{spans_block}}

Return strictly the JSON described above.
```

`library_block` is one of:
- *with entry:* `LIBRARY ENTRY (authoritative phrasing — preserve closely):\n  <text>`
- *without:* `LIBRARY ENTRY: none — produce a fresh draft from the bundle.`

`spans_block` entries:
```
span_id=<id>
  source=<doc>  form=<10-K|...>  anchor=page 17 | Item 1A
  text: <first 700 chars, single-line>
```

---

## 4. `CitationVerifier` (validator)

**Role.** L02 guardrail #01 — protects against hallucinated citations. For
every `[span:<id>]` in the draft, fetches the canonical span text and asks
Claude whether the *claim immediately preceding the citation* is genuinely
supported by the span's text. Combined with a deterministic
`span_hash` resolution check.

**Sources**
- Agent: [`services/validator/agent.py`](../../services/validator/agent.py) (class `CitationVerifier`, v1.0.0)
- Prompt: [`services/validator/prompts/v1.0.0.md`](../../services/validator/prompts/v1.0.0.md)
- I/O schema: `CitationVerifierInput`, `CitationVerifierOutput`, `CitationCheckResult`

**Frontmatter**

```yaml
agent: CitationVerifier
version: 1.0.0
model: claude-haiku-4-5
temperature: 0
max_tokens: 800
eval_set: validator_v0
```

**Inputs**
- `draft_text: str`
- `citations: list[CitationRef]` — `(span_id, doc_hash, span_hash, excerpt)`
- `span_lookup: dict[str, str]` — `span_hash → canonical text`

**Outputs**
- `all_pass: bool` — only true when every citation is resolved (hash present
  in `span_lookup`) **and** the claim is judged supported by the LLM check
- `results: list[CitationCheckResult]` — per-citation `(span_hash, resolved,
  excerpt_matches_span, reason)`
- `summary: str` — short paragraph

**Two-pass design (in the wrapper)**
1. **Deterministic resolution.** Each citation's `span_hash` is looked up in
   `span_lookup`. Misses → `resolved=False` with reason `span_hash not found
   in current corpus snapshot`.
2. **Semantic check.** The model receives the draft + the resolved spans;
   per-citation `supports_claim` is merged onto the resolution result.
   Unresolved citations cannot pass the semantic check regardless of model
   verdict.

**Hard rules (extracted from prompt)**
1. Strict JSON output.
2. "Supports" = cited span substantively contains the claim. Paraphrase OK,
   meaning must match. Generic adjacency is NOT support.
3. Near-verbatim quote = strongest support.
4. Citation with no preceding claim (e.g. in a header) → `supports_claim:
   false` with reason `"no preceding claim"`.
5. **Conservative bias** — when in doubt, mark unsupported. False negatives
   re-route to SME (recoverable); false positives reach the client packet.

### System prompt (verbatim)

```
You are CitationVerifier for the BNY Agentic DDQ Response Platform — the L02 guardrail check that protects against hallucinated citations.

You receive: (a) a draft DDQ response that contains inline `[span:<span_id>]` citations, and (b) the canonical text of each span. For each `(claim, cited span)` pair, decide whether the *claim immediately preceding the citation* is genuinely supported by the cited span's text.

Rules:

1. **Output strictly JSON.** Schema:
   ```json
   {"all_pass": true | false,
    "results": [
      {"span_id": "<id>", "supports_claim": true | false, "reason": "<short>"}
    ],
    "summary": "<one short paragraph>"}
   ```

2. "Supports" means the cited span text *substantively contains* the claim — paraphrase is fine, but the meaning must be the same. Generic adjacency is NOT support (e.g. citing a span that says "we manage operational risk" to back a specific RTO target).

3. If the claim is a near-verbatim quote of the span, that is the strongest form of support.

4. If a citation has no preceding claim in the draft (e.g. citation in a header), `supports_claim: false` with reason "no preceding claim".

5. Conservative bias: when in doubt, mark `supports_claim: false`. False negatives are recoverable (re-route to SME); false positives leak into client-facing packets.

6. Do not add commentary outside the JSON.
```

### User template (verbatim)

```
DRAFT RESPONSE
{{draft_text}}

CITATIONS
{{citations_block}}

Return strictly the JSON described above.
```

`citations_block` entries:
```
span_id=<id>
  span_hash=<hash>
  text: <first 700 chars>
```

---

## 5. `ConsistencyChecker` (consistency)

**Role.** Detects *drift* between a fresh draft and prior shipped responses
for the same canonical_id (or topical neighbours). Sourced from the DuckDB
`response_register` in M1+; from a caller-supplied list today.

**Sources**
- Agent: [`services/consistency/agent.py`](../../services/consistency/agent.py) (class `ConsistencyChecker`, v1.0.0)
- Prompt: [`services/consistency/prompts/v1.0.0.md`](../../services/consistency/prompts/v1.0.0.md)
- I/O schema: `ConsistencyCheckerInput`, `ConsistencyCheckerOutput`, `PriorResponse`

**Frontmatter**

```yaml
agent: ConsistencyChecker
version: 1.0.0
model: claude-sonnet-4-5
temperature: 0
max_tokens: 800
eval_set: consistency_v0
```

**Inputs**
- `canonical_id`, `draft_text`
- `prior_responses: list[PriorResponse]` — `(run_id, sealed_at, canonical_id, response_text)`, up to 5, oldest-first

**Outputs**
- `consistent: bool` (true ⇔ `!drift_detected`)
- `drift_detected: bool`
- `notes: str`, `diff_summary: str | null`

**Wrapper safety nets**
- Zero prior responses → no LLM call; returns
  `consistent=true, drift_detected=false, notes="No prior shipped responses for this canonical_id."`.

**Hard rules**
1. Strict JSON output.
2. Drift examples (flag): "annually" vs "quarterly", "RTO 4h" vs "RTO 24h".
3. Non-drift examples (allow): reworded same scope, additive detail (e.g.
   NIST mapping) that doesn't contradict.
4. Zero priors ⇒ `consistent: true, drift_detected: false,
   diff_summary: null, notes: "no prior responses to compare"`.
5. Conservative bias: when in doubt about a numeric change, flag drift.

### System prompt (verbatim)

```
You are ConsistencyChecker for the BNY Agentic DDQ Response Platform.

You receive: (a) a fresh DDQ draft response for some canonical_id, and (b) up to 5 prior shipped responses for the *same* canonical_id (or the closest topical neighbors), with timestamps. Decide whether the fresh draft is materially consistent with what BNY has already told other clients on the same topic.

You are looking for *drift*, not stylistic variation:
- "We test our BCP plan annually" vs "We test our BCP plan quarterly" → drift.
- "Our RTO is 4 hours" vs "Our RTO is 24 hours" → drift.
- Rewording the same control language with the same scope → not drift.
- A newer draft *adding* a detail (e.g. NIST mapping) without contradicting old → not drift.

Rules:

1. **Output strictly JSON.** Schema:
   ```json
   {"consistent": true | false,
    "drift_detected": true | false,
    "diff_summary": "<one short paragraph or null>",
    "notes": "<short overall comment>"}
   ```

2. `consistent: false` ⇔ `drift_detected: true`.

3. If there are zero prior responses, return `consistent: true, drift_detected: false, diff_summary: null, notes: "no prior responses to compare"`.

4. Conservative bias: when in doubt about whether a numeric change is real drift vs. honest update, flag it (`drift_detected: true`). Reviewers can clear it.

5. Do not add commentary outside the JSON.
```

### User template (verbatim)

```
CANONICAL ID: {{canonical_id}}

FRESH DRAFT
{{draft_text}}

PRIOR SHIPPED RESPONSES (oldest first)
{{prior_block}}

Return strictly the JSON described above.
```

`prior_block` entries:
```
run_id=<id>  sealed_at=<ISO timestamp>
  text: <first 800 chars>
```

---

## 6. `PiiScrubber` (pii)

**Role.** L02 guardrail #04 — confidentiality scrub backstop on top of the
deterministic Presidio pass (Presidio integration scheduled for M1; the
regex pass in `_deterministic_scan` is the dev backstop).

**Two-pass architecture (in the wrapper):**
1. **Deterministic regex pass** — SSN, account number, email, ticket ID
   patterns. SSN/ACCOUNT match → halt; email/ticket → warn. Matches are
   redacted inline to `[REDACTED:<KIND>]` *before* the model sees the text.
2. **Contextual LLM pass** — runs on the regex-cleaned text to catch the
   things regex misses (internal client names, employee usernames, internal
   system names, over-shared dollar amounts).

**Sources**
- Agent: [`services/pii/agent.py`](../../services/pii/agent.py) (class `PiiScrubber`, v1.0.0)
- Prompt: [`services/pii/prompts/v1.0.0.md`](../../services/pii/prompts/v1.0.0.md)
- I/O schema: `PiiScrubberInput`, `PiiScrubberOutput`, `PiiFinding`

**Frontmatter**

```yaml
agent: PiiScrubber
version: 1.0.0
model: claude-haiku-4-5
temperature: 0
max_tokens: 600
eval_set: pii_v0
```

**Inputs**
- `draft_text: str`

**Outputs**
- `clean_text: str` — fully redacted draft (regex + LLM redactions merged)
- `findings: list[PiiFinding]` — every regex + LLM finding, each
  `(kind, span, severity)` where `severity ∈ {info, warn, halt}`
- `halt: bool` — true if any finding has `severity: "halt"`

**Hard rules (extracted from prompt)**
1. Strict JSON output.
2. `halt: true` only for clearly internal data that must never leave BNY:
   explicit employee names tied to roles, internal IPs, ticket IDs, named
   non-public clients.
3. Generic public references (SEC filings, regulators, named frameworks)
   are NOT findings.
4. Clean drafts → unchanged text, `findings: []`, `halt: false`.
5. Do not invent findings to look thorough (false positives create review
   fatigue).

**Finding `kind` taxonomy** (LLM pass): `INTERNAL_CLIENT`, `INTERNAL_SYSTEM`,
`EMAIL`, `PHONE`, `VENDOR`, `TICKET`, `EMPLOYEE`, `FINANCIAL`, `OTHER`.
Regex pass adds: `SSN` (halt), `ACCOUNT_NUMBER` (halt), `EMAIL` (warn),
`TICKET` (warn).

### System prompt (verbatim)

```
You are PiiScrubber for the BNY Agentic DDQ Response Platform — the L02 guardrail #04 (Confidentiality Scrub) backstop on top of the deterministic Presidio pass.

You receive: a DDQ draft response (already passed deterministic regex checks for SSNs and bare account numbers).

Your job: detect and redact any *contextual* leakage that regex misses:
- Internal-only client names ("XYZ Pension Fund", "Acme Capital LLC") that aren't already public.
- Internal system names, ticket IDs, employee usernames, internal URLs.
- Specific dollar amounts, RTO/RPO targets, or vendor names that look like they were over-shared.
- Quoted email/phone of a specific named employee.

Generic public references are fine (e.g. SEC filings, named regulatory frameworks, "the Federal Reserve").

Rules:

1. **Output strictly JSON.** Schema:
   ```json
   {"clean_text": "<draft with redactions applied — replace each finding span with [REDACTED:<kind>]>",
    "findings": [
       {"kind": "<INTERNAL_CLIENT|INTERNAL_SYSTEM|EMAIL|PHONE|VENDOR|TICKET|EMPLOYEE|FINANCIAL|OTHER>",
        "span": "<short excerpt of what was redacted>",
        "severity": "info" | "warn" | "halt"}
    ],
    "halt": true | false}
   ```

2. `halt: true` if ANY finding has `severity: "halt"`. Use halt for clearly internal data that should never leave BNY: explicit employee names tied to roles, internal IP addresses, ticket IDs, named non-public clients.

3. If the draft is clean, return it unchanged with `findings: []` and `halt: false`.

4. Do not invent findings to look thorough. False positives create review fatigue.

5. Do not editorialize. Strict JSON only.
```

### User template (verbatim)

```
DRAFT TEXT
{{draft_text}}

Return strictly the JSON described above.
```

> **Note:** the `{{draft_text}}` passed to the LLM is the **post-regex**
> cleaned text. Regex findings (SSN, account numbers, plain emails, ticket
> IDs) are already redacted to `[REDACTED:<KIND>]` and recorded separately —
> the LLM's job is contextual leakage only.

---

## 7. `FreshnessAuditor` (rule-based; no prompt)

**Role.** Flags stale library entries and stale evidence. **Not an LLM
agent** — runs the Rule Engine DSL (see [`docs/specs/rule-engine.md`](../specs/rule-engine.md))
against active rules tagged `engine="freshness"`. Falls back to a hardcoded
decision tree when no `RuleRepository` is wired, so legacy fixtures keep
working.

**Sources**
- Agent: [`services/freshness/agent.py`](../../services/freshness/agent.py) (class `FreshnessAuditor`, v1.1.0)
- I/O schema: `FreshnessAuditorInput`, `FreshnessAuditorOutput`
- Rule engine: [`core/domain/rules.py`](../../core/domain/rules.py),
  [`core/ports/rules.py`](../../core/ports/rules.py)

**Inputs**
- `library_entry: dict | null` — must carry `expiry_date`, `review_due`, `tags`
- `evidence_bundle: list[EvidenceSpan]` — same shape as DraftComposer
- `today: str` — ISO date, supplied by orchestrator (testable)

**Outputs**
- `stale: bool`
- `reasons: list[str]` — one line per fired rule
- `oldest_evidence_date: str | null`

**Legacy decision logic (no rule engine):**
| Trigger | Reason |
|---|---|
| `library_entry.expiry_date < today`     | "library entry expired on <date>" |
| `library_entry.review_due < today`      | "library entry overdue for review since <date>" |
| `"bootstrap" in library_entry.tags`     | "library entry is bootstrap-tagged — needs SME re-approval" |
| Pillar 3 evidence > 12 months          | "pillar3 evidence <doc_id> is Nmo old (cap 12mo)" |

Annual (10-K, DEF 14A, 20-F) cap: 24 months. Quarterly (10-Q) cap: 18 months.
See `ANNUAL_MAX_DAYS`, `QUARTERLY_MAX_DAYS`, `PILLAR3_MAX_DAYS` in
[`services/freshness/agent.py`](../../services/freshness/agent.py).

**Context surfaced to the rule DSL** (`_build_context`):
```jsonc
{
  "library_entry": { "expiry_date": "...", "review_due": "...", "tags": [...] },
  "evidence":       [ <EvidenceSpan dumps> ],
  "evidence_oldest": { "pillar3_date": "<ISO>|null" },  // only set when stale
  "today": "<ISO>"
}
```
The DSL can't iterate lists yet, so the agent pre-computes aggregates
(currently `evidence_oldest.pillar3_date`) and surfaces them as dotted-path
addressable fields.

---

## 8. `ApprovalRouter` (rule-based; no prompt)

**Role.** Routes a question to `auto_approve` / `sme_queue` / `legal_review`
/ `halt`, picks the SME queue by canonical domain, and assigns the model tier
that the orchestrator should use for this question. **Not an LLM agent** —
rule-engine driven, with a legacy decision tree as fallthrough.

**Sources**
- Agent: [`services/router/agent.py`](../../services/router/agent.py) (class `ApprovalRouter`, v1.1.0)
- I/O schema: `ApprovalRouterInput`, `ApprovalRouterOutput`

**Inputs (the "rollup" of every guardrail signal)**
- `canonical_id: str | null`
- `classify_confidence: float`
- `validate_verdict: "pass" | "halt" | "escalate"`
- `pii_halt: bool`
- `freshness_stale: bool`
- `consistency_drift: bool`

**Outputs**
- `route: "auto_approve" | "sme_queue" | "legal_review" | "halt"`
- `queue: "infosec" | "cyber" | "esg" | "regulatory" | "ops" | "legal" | null`
- `tier: "tier1" | "tier2" | "tier3"`
- `rationale: str`

**Canonical → queue map** (`DOMAIN_QUEUE`)
| Canonical prefix | Queue |
|---|---|
| `canon.is`    | infosec |
| `canon.cyber` | cyber |
| `canon.esg`   | esg |
| `canon.reg`   | regulatory |
| `canon.subc`  | ops |
| `canon.or`    | ops |
| (default)     | ops |

**Canonical → tier map**
- Tier-1 (Opus, regulatory/security/cyber): `canon.reg.*`, `canon.cyber.*`, `canon.is.*`
- Tier-3 (Haiku, boilerplate): *(none yet)*
- Tier-2 (Sonnet): everything else

**Legacy decision tree (priority order)**

1. `pii_halt` → `halt` to **legal** queue. "PiiScrubber raised halt …"
2. `validate_verdict == "halt"` → `halt` to **legal**. "Validator halted …"
3. `freshness_stale` → `sme_queue` to domain queue. "FreshnessAuditor flagged stale …"
4. `consistency_drift` → `sme_queue` to domain queue. "ConsistencyChecker flagged drift …"
5. `classify_confidence < 0.70` → `sme_queue`. "Classify confidence X below 0.70."
6. `tier == "tier1"` → `sme_queue`. "Tier-1 canonical always requires SME sign-off."
7. otherwise → `auto_approve`. "All guardrails pass; auto-approves."

**Rule-engine mode.** When a `RuleRepository` is injected with rules tagged
`engine="approval"`, the engine evaluates them in priority order and the
**first match wins**. The fired rule's verdict shape is:

```jsonc
{
  "route":     "auto_approve" | "sme_queue" | "legal_review" | "halt",
  "queue":     "<optional override>",  // falls back to DOMAIN_QUEUE
  "rationale": "<text>"                // falls back to rule.title
}
```

Tier is always computed from the canonical_id; rules cannot override it.

---

## Adding a new prompt version

1. Copy `services/<svc>/prompts/v<X.Y.Z>.md` → `v<X.Y.Z+1>.md` and edit.
   Keep frontmatter accurate (model, temperature, max_tokens, eval_set).
2. Run the agent's eval slice (`evals/runners/<svc>.py` when M1 lands) and
   confirm regression metrics hold.
3. Flip the active marker: write the new version string to
   `services/<svc>/prompts/active.txt` (one line, no `v` prefix).
4. Update this catalog (frontmatter table, verbatim system/user blocks,
   rule changes). Don't ship the prompt edit without the doc edit — the
   "verbatim system prompt" blocks are the SME-facing artifact during
   incident review.
5. Promotion to prod still goes through the AutoGen Lite UI; the file
   edits + this doc are how engineers stage a change for SMEs to flip.
