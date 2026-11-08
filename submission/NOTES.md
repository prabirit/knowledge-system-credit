# Submission notes

## Approach

This submission uses a deterministic, dependency-free Python implementation of the assignment contract. `build()` returns a system with `ingest()`, `answer()` and `conflicts()`.

### Why deterministic rules and a temporal fact store?

The assignment primarily tests whether the system selects the right value for the right product, tier and date—not whether it can hold a long conversation or plan actions. Many errors in the supplied data arise from stale pages, mismatched tiers, and rate/APY confusion. Explicit parsing and ranking rules make those decisions inspectable and repeatable: equivalent questions produce stable answers, sources can be cited, and old or unsupported values can be rejected deliberately.

The scorer also rewards low answer latency (full speed credit at p95 <= 2 seconds), and the grading environment is a clean Python 3.11 environment where no API key or model service can be assumed. Avoiding runtime model calls removes network latency, rate limits, API-key requirements and output variation. It also avoids sending the event's website content to an external service. The public eval and bundled self-test can run entirely offline.

### Why not a full knowledge graph or vector-only RAG?

A full graph database is unnecessary for this corpus and question set: the scorer supplies only a few thousand small page versions, and questions mostly ask for one fact, its qualifiers, or its historical value rather than complex multi-hop relationships. Operating a graph service would add deployment and dependency requirements without a clear scoring benefit.

Vector-only RAG is also a poor fit for the highest-risk questions. Similar text can retrieve a stale calculator value alongside an official rate, and semantic similarity alone does not establish which one is current or whether two rates belong to different tiers. Instead, the core is a small **graph-like temporal fact model**: facts retain their product, attribute, qualifiers, value, source, authority and snapshot date. Deterministic filters and source ranking handle structured questions; lexical passage retrieval is a lightweight fallback for prose. This keeps the useful structure of a knowledge graph without a graph database or model dependency.

- **Ingestion:** keeps each snapshot and page version in memory, splits Markdown into table rows and prose passages, and records source URL, snapshot date and page authority.
- **Answering:** selects a snapshot by `as_of`, applies deterministic routing for structured information (rates, branch hours/addresses, membership and product lists), then falls back to lexical retrieval. Where specific rate or branch evidence is absent, it declines rather than fabricating a value.
- **Conflicts:** normalizes table attributes and values, retains product qualifiers such as term, balance tier and model year, reports current-snapshot disagreements, and separately detects stale model-year vehicle-rate rows. Preferred values are selected by source authority and recency.

The store and search index are rebuilt by `ingest()` for each scorer run. No external database, network calls, LLM, embedding service or API key is needed. No snapshot content is included as a generated data file in this submission.

## Verification

From the repository root:

```bash
python3 -m unittest submission.test_regressions
python3 harness/run_eval.py --submission submission --snapshots harness/selftest/snapshots --eval harness/selftest/eval.jsonl --conflicts-gold harness/selftest/conflicts_gold.json
python3 harness/run_eval.py --submission submission --eval eval/public_eval.jsonl
```

The assignment grader uses Python 3.11. The regression tests, bundled self-test and public eval have been run locally with Python 3.11.
