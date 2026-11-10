# Submission notes

## Approach

This submission uses a deterministic, dependency-free Python implementation of the assignment contract. `build()` returns a system with `ingest()`, `answer()` and `conflicts()`.

### Why deterministic rules and a temporal fact store?

The assignment primarily tests whether the system selects the right value for the right product, tier and date—not whether it can hold a long conversation or plan actions. Many errors in the supplied data arise from stale pages, mismatched tiers, and rate/APY confusion. Explicit parsing and ranking rules make those decisions inspectable and repeatable: equivalent questions produce stable answers, sources can be cited, and old or unsupported values can be rejected deliberately.

The scorer also rewards low answer latency (full speed credit at p95 <= 2 seconds), and the grading environment is a clean Python 3.11 environment where no API key or model service can be assumed. Avoiding runtime model calls removes network latency, rate limits, API-key requirements and output variation. It also avoids sending the event's website content to an external service. The public eval and bundled self-test can run entirely offline.

### Why not a full knowledge graph or vector-only RAG?

A full graph database is unnecessary for this corpus and question set: the scorer supplies only a few thousand small page versions, and questions mostly ask for one fact, its qualifiers, or its historical value rather than complex multi-hop relationships. Operating a graph service would add deployment and dependency requirements without a clear scoring benefit.

Vector-only RAG is also a poor fit for the highest-risk questions. Similar text can retrieve a stale calculator value alongside an official rate, and semantic similarity alone does not establish which one is current or whether two rates belong to different tiers. Instead, every table row is kept per snapshot with its product, qualifiers (term, tier, model year), value, source page, authority rank and in-page effective date. Targeted handlers read the right row for the question; an IDF-weighted keyword scorer is the fallback for prose. Conflicts use the same rows, grouped by product, qualifiers and attribute. This keeps the useful structure of a knowledge graph without a graph database or model dependency. See `docs/ARCHITECTURE.md` for the as-built design.

- **Ingestion:** keeps each snapshot and page version in memory, splits Markdown into table rows and prose passages, and records source URL, snapshot date and page authority.
- **Answering:** selects a snapshot by `as_of`, declines specific rate or branch questions with no published evidence, then tries targeted handlers (rates by term and tier, mortgage tiers, branch addresses and hours, product lists, membership, dated prose facts). Each handler reads its value from the matching page in that snapshot, never from fixed answer text. Otherwise it falls back to keyword retrieval with expiry, term and model-year filters.
- **Conflicts:** normalizes table attributes and values, retains product qualifiers such as term, balance tier and model year, reports current-snapshot disagreements, and separately detects stale model-year vehicle-rate rows. Preferred values are selected by source authority and recency.

The store and search index are rebuilt by `ingest()` for each scorer run. No external database, network calls, LLM, embedding service or API key is needed. No snapshot content is included as a generated data file in this submission.

## Caveats, AI strategy and future improvements

The current implementation is a tested hackathon submission, but its practice-set scores are not a guarantee of hidden-test performance. Important caveats:

- **Development scores are not independent validation.** The public eval is official practice data; the hold-out and 124-question set were used to find bugs and tune handlers. Passing them is a regression signal, not an estimate of the hidden score.
- **Conflict gold is incomplete.** The bundled self-test has one conflict. The development gold list has 13 manually labelled conflicts, while the detector reports more. Unmatched conflicts need human review before claiming precision or recall against the hidden set.
- **The certificate-list public item is under-specified by its scorer.** Its `must_include` list is empty, which the harness scores as zero correctness even though the answer lists all 12 terms. A dedicated regression test checks the content; do not add unrelated text to game the score.
- **“Current” means “latest captured snapshot”.** Changes between snapshots, including a value that changes and reverts between crawls, cannot be known. For a date with no snapshot, the system uses the latest earlier snapshot or declines before the first snapshot; it cannot guarantee what the live site showed that day.
- **Source authority is a heuristic.** Official rates pages usually outrank product pages, promos, calculators and articles, but a product page can itself be stale. New conflicts should be checked against effective/expiry dates and page context.
- **Routing patterns are still hand-authored.** They are centralized in `knowledge/routing.py` and answer logic is split by fact type, but new wording or changed page structure may bypass a handler and use the weaker keyword fallback.

The deterministic design trades flexibility for predictability. Its main implementation limitations are:

- **Website layout changes:** extraction depends on recognizable URLs, page types, Markdown tables, headings and phrasing. A redesigned rates page, renamed columns, or moved branch listing could make facts disappear or be misclassified. When the site changes, review the page classifier, table parser and source-ranking rules first.
- **Hand-written routing:** many intents (mortgage tiers, auto-loan model years, branch hours, membership, product lists and several prose facts) have targeted handlers keyed to specific page paths and phrasings. Values come from the pages, but *which* page and *which* phrasings trigger a handler are hard-coded, so a renamed page, a new product or an unanticipated wording can bypass a handler and fall through to the weaker keyword fallback. Each fact type has its own module under `submission/knowledge/handlers/`, and every trigger pattern now lives in one table, `submission/knowledge/routing.py`, so triggers can be audited and extended in one place. The phrasings are still hand-written regular expressions, so an unanticipated wording can still miss a handler; that remains the main limitation.
- **Paraphrase coverage:** lexical retrieval and the alias list cover common wording, but unusual paraphrases with little word overlap may miss the correct passage. If hidden or production questions show that pattern, add a local or optional embedding/re-ranking step as a fallback, keeping deterministic fact selection for numeric answers.
- **Prose extraction depth:** structured tables are handled more reliably than long narrative pages, PDFs and spreadsheets. Facts embedded in prose may need additional extractors, or an optional ingest-time LLM extractor with cached outputs and a rules-only fallback.
- **Temporal gaps:** snapshots are point-in-time observations. A value that changed and reverted between crawls cannot be observed, and an `as_of` answer reflects the latest captured snapshot, not necessarily every real-world update. Dates outside the snapshot range need explicit handling and clear communication.
- **Conflict precision:** conflicts are reported only when normalized product, qualifiers and attribute match. New qualifier types, inconsistent product names, or stale pages that use different labels can cause false positives or missed conflicts. Maintain a reviewed set of real conflicts and false-positive examples, and use it as regression data.
- **Authority assumptions:** the current ordering prefers official rate pages and product pages over calculators, promotions, blogs and newsroom items. That assumption can be wrong when a product page is stale or a promotion is current. Effective dates, expiry dates and page-specific exceptions should be expanded as more evidence becomes available.
- **Scale / data storage:** the in-memory store and per-question candidate scoring are appropriate for this snapshot set and the grader, which rebuilds the system by calling `ingest()`. For a much larger or continuously updated corpus, move snapshot metadata and normalized, qualified fact records to PostgreSQL (or another managed relational database); keep the original Markdown/PDF files in object storage or a filesystem and store stable references to them in the database. Add indexes for product, attribute, qualifiers and snapshot/effective dates, plus a precomputed full-text index, so queries do not scan every page. A vector index (for example, pgvector) is optional only if measured paraphrase failures justify it. Keep the `ingest()` / `answer()` / `conflicts()` interface and put persistence behind a storage adapter. A graph database is not currently justified: the known workload is temporal fact lookup and conflict resolution, not complex multi-hop traversal.

### Why this version does not call an AI model

This is a deliberate scope choice, not a claim that AI has no value. The assignment's hardest cases are factual: choose the right number, tier, source and snapshot date, or decline. Those decisions are safer to audit as explicit rules over evidence-bearing table rows than to delegate to a generative model. The grader also runs in a clean environment, rewards p95 answer times under two seconds, and does not guarantee an API key. Avoiding an LLM at answer time therefore removes network latency, quota / availability risk and output variation. The current system is not an autonomous agent: there are no actions or tools for an agent to plan or invoke.

AI could be valuable if the system grows beyond this fixed snapshot challenge, especially for:

- **Ingest-time extraction of unstructured documents:** a model can propose typed facts from prose, PDFs or changed table layouts. Keep the source quote, URL, snapshot and effective date with every proposed fact; validate the quote and schema deterministically, and send ambiguous extractions for review. Never accept an unsupported value.
- **Question understanding:** a model can map unfamiliar wording to an intent, product and qualifiers. Use it to produce a structured query, then let deterministic retrieval and authority rules choose the answer.
- **Semantic search for prose:** embeddings or a model-assisted reranker can improve paraphrase retrieval where lexical overlap is weak. Keep exact rates, dates and tiers in the structured fact path.
- **Evaluation and drift review:** a model can suggest new paraphrases or flag pages whose structure changed, but test those suggestions against source evidence and a versioned evaluation set.

For a production version, I would evaluate these as optional hybrid components one at a time. Compare accuracy, grounded citations, latency, consistency, cost, privacy and failure rate against the deterministic baseline. A model should not override conflicting official evidence or turn an unknown into a guess; a full agent or graph database is only warranted if future requirements add multi-step relationships or actions.

### Recommended future improvements

Prioritize changes by evidence from evaluation failures:

1. **Improve conflict precision.** Manually review the 33 current conflict outputs, expand `dev/conflicts_gold80.json` only with verified conflicts, and add negative examples for tier differences, duplicate pages, APR-vs-rate and stale historical changes.
2. **Add independent paraphrases and date-boundary tests.** Keep question groups separate from examples used to tune code. Test every snapshot boundary, new/removed products, and dates inside the large June–August gap.
3. **Broaden fact extraction where real misses occur.** Add reusable parsers for new table layouts, branch records and page-effective dates. Avoid adding a special-case answer when the same fact can be read from the source row.
4. **Improve semantic fallback only if measured misses justify it.** A local embedding or cached ingest-time model could help with prose paraphrases; keep rate/tier decisions deterministic and retain a no-network fallback.
5. **Refactor and scale only when needed.** If the corpus grows beyond a few thousand page versions or becomes continuously updated, precompute a persistent fact/search index. The current in-memory design is intentionally simpler for the supplied batch.
6. **Re-run verification under Python 3.11** after every behavior change; compare golden outputs for refactors and update regression tests when changed behavior is intentional.

## Verification

From the repository root:

```bash
python3 -m unittest discover -s submission -p "test_*.py"
python3 harness/run_eval.py --submission submission --snapshots harness/selftest/snapshots --eval harness/selftest/eval.jsonl --conflicts-gold harness/selftest/conflicts_gold.json
python3 harness/run_eval.py --submission submission --eval eval/public_eval.jsonl
python3 harness/run_eval.py --submission submission --eval dev/holdout_eval.jsonl
```

The assignment grader uses Python 3.11. The regression tests, bundled self-test and public eval have been run locally with Python 3.11.
