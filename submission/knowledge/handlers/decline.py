"""Decline gate: refuse specific rate / branch questions the website does not publish."""
from __future__ import annotations

import re

from ..routing import INTENTS, all_of, has
from ..text import tokenize


def should_decline(question: str, target: str, store):
    """Decline specific rate/location asks unless official evidence states the fact.

    This is a conservative evidence gate, not a question-specific answer: it checks
    whether the selected snapshot contains a matching official table row or a
    location-specific hours record.
    """
    q = question.lower()
    official_rows = [r for r in store.rows_by_snapshot.get(target, []) if r["rank"] <= 2]
    rate_question = has("rate_question", q)

    # Adjustable products and construction loans require an explicitly matching
    # official rate row; a general mortgage rate or descriptive blog is not enough.
    specialized_rate_terms = []
    if has("specialized_rate_ask", q):
        specialized_rate_terms.extend(("adjustable", "7/1", "arm"))
    if has("construction_subject", q) and rate_question:
        specialized_rate_terms.append("construction")
    if rate_question and specialized_rate_terms:
        matching = []
        for row in official_rows:
            body = row["body"].lower()
            has_requested_product = any(term in body for term in specialized_rate_terms)
            has_published_rate = has("rate_present", body)
            if has_requested_product and has_published_rate:
                matching.append(row)
        if not matching:
            return True

    # A named branch/location hours question must be supported by a location-specific
    # official page, not by general call-center hours or an unrelated historical article.
    if all_of(q, "branch_location_subject", "location_hours_open"):
        place_match = re.search(INTENTS["named_location_phrase"][0], q)
        if place_match:
            place = place_match.group(1).strip()
            generic = {"dupaco", "all dupaco", "all", "any", "each", "general"}
            if place not in generic:
                place_tokens = tokenize(place)
                location_evidence = []
                for page in store.pages_by_snapshot.get(target, []):
                    if page["rank"] > 2:
                        continue
                    body = page["text"].lower()
                    if not place_tokens or not all(t in tokenize(body) for t in place_tokens):
                        continue
                    has_specific_hours = has("location_time", body)
                    if has_specific_hours:
                        location_evidence.append(page)
                if not location_evidence:
                    return True
    return False
