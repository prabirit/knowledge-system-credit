# Submission notes

## Approach

This submission is a deterministic, dependency-free Python implementation of the assignment contract. `build()` returns a system with `ingest()`, `answer()` and `conflicts()`.

- **Ingestion:** keeps each snapshot and page version in memory, splits Markdown into table rows and prose passages, and records source URL, snapshot date, and page authority.
- **Answering:** selects a snapshot by `as_of`, applies deterministic routing for well-known structured information (rates, branch hours/addresses, membership, and product lists), then falls back to lexical retrieval. Where specific rate or branch evidence is absent, it declines rather than fabricating a value.
- **Conflicts:** normalizes table attributes and values, retains product qualifiers such as term, balance tier and model year, reports current-snapshot disagreements, and separately detects stale model-year vehicle-rate rows. Preferred values are selected by source authority and recency.

The store and search index are rebuilt by `ingest()` for each scorer run. No external database, network calls, LLM, embedding service, or API key is needed. No snapshot content is included as a generated data file in this submission.

## Verification

From the repository root:

```bash
python3 -m unittest submission.test_regressions
python3 harness/run_eval.py --submission submission --snapshots harness/selftest/snapshots --eval harness/selftest/eval.jsonl --conflicts-gold harness/selftest/conflicts_gold.json
python3 harness/run_eval.py --submission submission --eval eval/public_eval.jsonl
```

The assignment grader uses Python 3.11. Run the commands with Python 3.11 in the grading environment; the development machine used for the latest local checks had Python 3.14, and Python 3.11 was not installed there.
