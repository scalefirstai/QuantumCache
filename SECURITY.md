# Security policy

## Reporting a vulnerability

**Please do not file public issues for security vulnerabilities.**

Use GitHub's private vulnerability reporting:
<https://github.com/scalefirstai/QuantumCache/security/advisories/new>

That channel routes directly to the maintainers and stays confidential
until a fix is published.

We acknowledge reports within 3 business days and aim to ship fixes for
critical-severity issues within 14 days of confirmation. Lower-severity
issues are batched into the next normal release cycle.

## Scope

This repository implements the BNY DDQ response platform — a stack of
LLM agents, retrieval services, and audit infrastructure. Things in
scope for security reports:

- Authentication / authorization bypasses (when Okta + OPA land).
- Tenant-data leakage across runs, library entries, or DDQ packets.
- Prompt-injection that crosses guardrails (CitationVerifier,
  PiiScrubber, ConsistencyChecker, FreshnessAuditor).
- Audit-journal forgery — anything that breaks the Merkle / hash-chain
  guarantees in `apps/orchestrator/main.py` or the L01 service.
- Supply-chain issues in dependencies (Python + npm); please prefer
  Dependabot for routine CVE reporting.

Out of scope:

- Issues that require running the orchestrator with attacker-controlled
  `torch.load` checkpoints. We never load untrusted checkpoints; the
  embedding model is fetched once from HuggingFace over TLS.
- DoS via local CPU/memory exhaustion on the dev box.
- Vulnerabilities in third-party services we depend on (LocalStack,
  OpenSearch, Qdrant, MongoDB) — report those upstream.

## Supported versions

The repository currently has a single `main` branch under active
development. Security fixes target `main` only until a tagged release.
