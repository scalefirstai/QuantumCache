# BNY Agentic DDQ Response Platform — `ddq-platform`

Build contract: [`docs/ddq.md`](docs/ddq.md) (the spec).
Data plan: [`docs/DATA-PLAN.md`](docs/DATA-PLAN.md) (what to build before L01–L08 land).

## Status

**M0 — Day 1–2 (vendor public files + hash) in progress.**

| Phase | Source | Status |
|---|---|---|
| Day 1–2 — Vendor & verify | DATA-PLAN §8 | done |
| Day 3–4 — EDGAR & IR ingest | DATA-PLAN §8 | done (ADV deferred to Day 8 per plan) |
| Day 5 — Parse to spans | DATA-PLAN §8 | done — 13,466 spans, deterministic, hash-integrity PASS |
| Day 6 — Lexical index (OpenSearch BM25) | DATA-PLAN §8 | done — `spans-v1` index, 6/7 smoke queries PASS |
| Day 7 — Dense index + hybrid retrieval | DATA-PLAN §8 | done — Qdrant `spans_v1`, BGE-small-en-v1.5, RRF fusion, 7/7 PASS |
| Day 8 — Taxonomy v0.1 cut | DATA-PLAN §8 | done — 548 canonical IDs across 6 domains; signed snapshot; 4/4 §4.5 acceptance PASS (ADV deferred) |
| Day 9 — Library v0 (~50 entries) | DATA-PLAN §8 | done — 60 entries via hybrid retrieval over BNY public corpus; 4/4 §5.4 PASS (replay deferred to L01) |
| Day 10 — Eval set v0 + harness | DATA-PLAN §8 | done — 100 items, baseline at recall@10=56% / halt_rate=36%; thresholds locked, CI-ready |
| Day 13–14 — Wire it up end-to-end | DATA-PLAN §8 | done — L07 graph runs on 5 eval items; journal chain + Merkle root verified; sealed to `bny-ddq-runs-sealed/` |
| Day 8–9 — Canonical taxonomy v0.1 | DATA-PLAN §8 | not started |
| Day 10–11 — Library v0 | DATA-PLAN §8 | not started |
| Day 12 — Eval set v0 | DATA-PLAN §8 | not started |
| Day 13–14 — Wire it up | DATA-PLAN §8 | not started |

## Quick start

```bash
# 0. one-time: venv with boto3 (used by Day 3+ scripts to write to LocalStack)
python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip boto3

# 1. bring up LocalStack (creates 5 S3 buckets via init hook)
mkdir -p infra/docker/volume/{localstack,mongo,redis,opensearch,qdrant,neo4j/data,neo4j/logs}
docker compose -f infra/docker/docker-compose.yml up -d localstack

# 2. Day 1-2: vendor public framework sources + verify
python3 data/bootstrap/fetch_sources.py
python3 data/bootstrap/verify_sources.py

# 3. Day 3-4: BNY public corpus ingest into LocalStack S3
.venv/bin/python data/bootstrap/01_fetch_edgar.py    # 106 SEC filings, ~134 MB
.venv/bin/python data/bootstrap/02_fetch_bny_ir.py   # 20 Pillar 3 PDFs, ~8.7 MB
.venv/bin/python data/bootstrap/materialize_documents.py  # combined index + §3.6 acceptance

# 4. Day 5: parse the corpus + framework sources into evidence spans
.venv/bin/pip install -q -r requirements-bootstrap.txt   # adds bs4, pymupdf, python-docx, pyarrow
.venv/bin/python data/bootstrap/03_parse_corpus.py        # 13,466 spans -> parquet shadow per source
.venv/bin/python data/bootstrap/04_verify_spans.py        # hash + determinism acceptance

# 5. Day 6: lexical (BM25) index in OpenSearch
docker compose -f infra/docker/docker-compose.yml up -d opensearch
.venv/bin/python data/bootstrap/05_index_opensearch.py    # spans-v1 index, ddq_text analyzer
.venv/bin/python data/bootstrap/06_query_smoke.py         # 7-query smoke test

# 6. Day 7: dense vectors in Qdrant + hybrid retrieval
docker compose -f infra/docker/docker-compose.yml up -d qdrant
.venv/bin/pip install -q -r requirements-bootstrap.txt    # adds sentence-transformers, qdrant-client
PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 \
  .venv/bin/python data/bootstrap/07_index_qdrant.py      # ~5 min on M-series GPU
.venv/bin/python data/bootstrap/08_hybrid_query.py        # BM25 + dense + RRF (k=60)

# 7. Day 8: taxonomy v0.1 — Mongo live + signed snapshot to S3
docker compose -f infra/docker/docker-compose.yml up -d mongo
PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 \
  .venv/bin/python data/bootstrap/09_build_taxonomy.py    # 548 canonical IDs, signed tx_v0.1

# 8. Day 9: library v0 — extractive entries from BNY public corpus
PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 \
  .venv/bin/python data/bootstrap/10_seed_library.py      # 60 entries, signed lib_v0.1

# 9. Day 10: eval set v0 (100 items) + baseline harness
.venv/bin/python evals/runners/build_eval_v0.py           # writes evals/fixtures/v0/eval_set.json
PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 \
  .venv/bin/python evals/runners/run_eval_v0.py           # baseline -> evals/reports/v0-baseline.json

# 10. Day 13-14: wire it up end-to-end on 5 eval items
PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 \
  .venv/bin/python data/bootstrap/11_wire_up.py           # L07 graph -> sealed runs in S3
```

After Day 3-4, `s3://bny-ddq-knowledge-raw/` holds 126 objects (~143 MB) under `edgar/bny-mellon-corp/` and `bny-ir/bny-mellon-corp/`. The combined `data/manifests/knowledge-documents.json` is the offline shadow of the Mongo `knowledge.documents` collection (ddq.md §5).

## Repo layout

Per `docs/ddq.md` §3. Most service / app dirs are scaffold-only until M1.

- `data/` — bootstrap pipeline (DATA-PLAN §7). Self-contained; no SPEC interface deps yet.
- `infra/docker/` — LocalStack + supporting backends for dev (DATA-PLAN §3.2, ddq.md §9.3).
- `core/`, `services/`, `apps/`, `packages/`, `evals/`, `tests/` — empty scaffolds; populated in M1+.
- `docs/` — `ddq.md` (spec), `DATA-PLAN.md`, `decisions/` (ADRs), `runbooks/`.

## Python version

`docs/ddq.md` §2 specifies Python 3.12. Day 1–2 scripts are stdlib-only and run on 3.9+. Pinning 3.12 is enforced in `pyproject.toml` once we add real dependencies (M1).
