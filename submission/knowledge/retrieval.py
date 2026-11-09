"""Keyword fallback: IDF-weighted scoring of table rows and passages."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from contract import Answer, Source  # noqa: E402

from .text import RANGE_RE, tokenize


def rank_candidate(item, query_terms, question, doc_frequency, n_docs):
    """Score one row or passage: IDF-weighted keyword overlap plus authority and domain boosts."""
    overlap = query_terms & item["terms"]
    if not overlap:
        return 0.0
    # BM25-inspired IDF weights rare, discriminative terms (e.g. routing, Hy-Vee)
    # more heavily than common words (e.g. account, rate).
    score = sum(1.0 + __import__("math").log((n_docs + 1) / (doc_frequency.get(t, 0) + 1)) for t in overlap)
    coverage = len(overlap) / max(1, len(query_terms))
    score += coverage * 2.0
    if item["kind"] == "table":
        score += 1.5
    score += max(0, 7 - item["rank"]) * 0.25
    q = question.lower()
    path = urlparse(item["url"]).path.lower()
    if re.search(r"\b(auto|vehicle|car)\b", q) and ("auto" in path or "motorcycle" in path):
        score += 3.0
    if re.search(r"\b(mortgage|home loan)\b", q) and ("home-loan" in path or path.endswith("/rates")):
        score += 3.0
    if re.search(r"\b(certificate|cd)\b", q) and (path.endswith("/rates") or "savings-account" in path):
        score += 2.0
    if "business" in q and "business" in path:
        score += 2.0
    # Prefer exact question qualifiers in a table row: term, year, balance tier.
    if item["kind"] == "table":
        for pattern in (r"\b\d+\s*[- ]?\s*months?\b", r"\b\d{4}\b", r"\$\s?[\d,]+"):
            for match in re.findall(pattern, q):
                if tokenize(match) & item["terms"]:
                    score += 2.5
    return score


def keyword_answer(question: str, target: str, store):
    """Answer by IDF-weighted keyword retrieval when no targeted handler matched."""
    qterms = tokenize(question)
    if not qterms:
        return Answer("I don't know; I couldn't identify the requested information.", confident=False)
    candidates = store.rows_by_snapshot.get(target, []) + store.passages_by_snapshot.get(target, [])
    # Keep a last-known fact available when its page disappeared from a later full
    # crawl. Prefer current snapshot evidence whenever it exists; historical evidence
    # is only a fallback and remains clearly cited with its original snapshot date.
    if len(store.snapshots) > 1:
        all_candidates = []
        for snapshot_id, snapshot_date in store.snapshots:
            if snapshot_date <= target and snapshot_date != target:
                all_candidates.extend(store.rows_by_snapshot.get(snapshot_date, []))
                all_candidates.extend(store.passages_by_snapshot.get(snapshot_date, []))
    else:
        all_candidates = []
    # Drop expired offers for questions after their stated expiration date, but keep
    # them available for genuinely historical as-of questions.
    candidates = [item for item in candidates
                  if item["rank"] < 99 or (item.get("expired_on") and target <= item["expired_on"])]
    # For term-specific certificate questions, don't let another term satisfy the
    # query. If the requested term is absent, decline rather than guessing.
    term_match = re.search(r"\b(\d{1,3})\s*[- ]?\s*months?\b", question.lower())
    if term_match and re.search(r"\b(certificate|certificates|cd)\b", question.lower()):
        term = int(term_match.group(1))
        term_candidates = [item for item in candidates
                           if re.search(r"\b{}\s*[- ]?\s*months?\b".format(term), item.get("body", "").lower())]
        if not term_candidates:
            return Answer("I couldn't find a published certificate rate for that term.", confident=False)
        candidates = term_candidates
    doc_frequency = {}
    for item in candidates:
        for term in item["terms"]:
            doc_frequency[term] = doc_frequency.get(term, 0) + 1
    scored = []
    for item in candidates:
        score = rank_candidate(item, qterms, question, doc_frequency, max(1, len(candidates)))
        if score > 0:
            scored.append((score, item))
    if not scored and all_candidates:
        historical = [item for item in all_candidates
                      if item["rank"] < 99 and item["kind"] != "table"]
        historical_scored = []
        for item in historical:
            score = rank_candidate(item, qterms, question, doc_frequency, max(1, len(candidates) + len(historical)))
            if score > 0:
                historical_scored.append((score, item))
        scored = historical_scored
    if not scored:
        return Answer("I couldn't find that information in the available website pages. Please contact Dupaco.", confident=False)
    # For vehicle-loan questions, enforce the requested term and model-year range
    # before lexical ranking. This prevents a calculator's stale but more keyword-rich
    # table from beating the authoritative loan-rate table.
    qlower = question.lower()
    if re.search(r"\b(auto|vehicle|car)\b", qlower):
        term_match = re.search(r"\b(\d{2,3})\s*[- ]?\s*months?\b", qlower)
        year_match = re.search(r"\b(20\d{2})\b", qlower)
        if term_match and year_match:
            requested_term = int(term_match.group(1))
            requested_year = int(year_match.group(1))
            qualified = []
            for score, item in scored:
                if item["kind"] != "table":
                    continue
                body = item["body"]
                row_term = re.search(r"\b(\d{2,3})\s*months?\b", body, re.I)
                if not row_term or int(row_term.group(1)) != requested_term:
                    continue
                ranges = RANGE_RE.findall(body)
                in_year_range = False
                older = re.search(r"(\d{4})\s+Model Year\s*\(and older\)", body, re.I)
                if older and requested_year <= int(older.group(1)):
                    in_year_range = True
                for start_s, end_s in ranges:
                    start, end = int(start_s), int(end_s)
                    if end < 100:
                        end = (start // 100) * 100 + end
                    if start <= requested_year <= end:
                        in_year_range = True
                        break
                # A row with no explicit range isn't evidence for a specific model year.
                if in_year_range:
                    qualified.append((score, item))
            authoritative = [(score, item) for score, item in qualified if item["rank"] <= 2]
            if authoritative:
                scored = authoritative
            elif qualified:
                scored = qualified
    scored.sort(key=lambda pair: (pair[0], -pair[1]["rank"], pair[1]["url"]), reverse=True)
    best_score, best = scored[0]
    if best_score < 2.0:
        return Answer("I couldn't find that information in the available website pages. Please contact Dupaco.", confident=False)
    # Broad list queries can span several official product pages; keep only strong,
    # same-domain matches to avoid mixing unrelated numbers into the answer.
    wants_list = bool(re.search(r"\b(all|list|what .* offer|what .* rates|rates for|interest rates|what are .* cards)\b", question.lower()))
    selected = [best]
    if wants_list:
        seen = {best["body"]}
        for score, item in scored[1:]:
            if score < best_score * 0.58 or item["kind"] != best["kind"]:
                continue
            if item["body"] in seen:
                continue
            if best["kind"] == "table" and item["rank"] > 2:
                continue
            selected.append(item)
            seen.add(item["body"])
            if len(selected) >= 12:
                break
    texts = []
    for item in selected:
        body = re.sub(r"^\|\s*|\s*\|$", "", item["body"])
        texts.append(body)
    text = "; ".join(texts)[:1800]
    sources = []
    for item in selected:
        if not any(s.url == item["url"] for s in sources):
            sources.append(Source(url=item["url"], snapshot_id=item["snapshot_id"], quote=item["body"][:300]))
    return Answer(text=text, sources=sources, confident=best_score >= 2.0)
