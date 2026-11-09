"""Resolve which snapshot date a question is about."""
from __future__ import annotations

import re
from calendar import month_name, monthrange
from datetime import date

from .text import parse_date

MONTH_YEAR_RE = re.compile(
    r"\b(?:as of|in)\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b",
    re.I)


def requested_date(question: str, as_of):
    """The date the member is asking about: the explicit ``as_of``, else a date written in the
    question (``06/15/2026`` or ``as of May 2026``, which means that month's last day), else None."""
    requested = as_of
    if not requested:
        requested = parse_date(question)
        if not requested:
            m = MONTH_YEAR_RE.search(question)
            if m:
                month = list(month_name).index(m.group(1).title())
                requested = date(int(m.group(2)), month, monthrange(int(m.group(2)), month)[1]).isoformat()
    return requested
