"""Text helpers shared by ingestion, handlers and retrieval: tokenising, aliases, dates."""
from __future__ import annotations

import re

WORD_RE = re.compile(r"[a-z0-9]+(?:[.$%][a-z0-9]+)*", re.I)
RANGE_RE = re.compile(r"\b(\d{4})\s*[-–]\s*(\d{2,4})\b")
TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}.*\|.*$\s*$")
DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
STOP = set("""
    a an the is are was were be been being do does did have has had what what's
    which who where when why how can could would should tell me please i we you
    your our dupaco of for to in on at by from with as and or it this that these
    those about current currently now today rate rates interest tell give find
    know offer offers account accounts loan loans savings their they them
""".split())
ALIASES = {
    "cd": "certificate", "certificates": "certificate", "certificate": "certificate",
    "apy": "apy", "apr": "apr", "auto": "auto vehicle", "car": "auto vehicle",
    "vehicle": "auto vehicle", "lobby": "branch lobby", "driveup": "drive up",
    "drive-up": "drive up", "checking": "checking account", "branch": "branch",
    "mortgage": "home loan", "jumbo": "jumbo", "hours": "hours",
}



def tokenize(text: str) -> set[str]:
    """Lower-case keyword set with year ranges expanded (2024-27 gives 2024..2027) and aliases added."""
    lowered = text.lower()
    out = set(WORD_RE.findall(lowered))
    # Expand compact year ranges such as 2024-27 so a 2025 question matches.
    for start_s, end_s in RANGE_RE.findall(lowered):
        start, end = int(start_s), int(end_s)
        if end < 100:
            end = (start // 100) * 100 + end
        if end >= start and end - start <= 20:
            out.update(str(year) for year in range(start, end + 1))
    for token in list(out):
        if token in ALIASES:
            out.update(ALIASES[token].split())
    return out - STOP



def parse_date(text: str):
    """First MM/DD/YYYY date in text as an ISO string, or None."""
    m = DATE_RE.search(text or "")
    if not m:
        return None
    month, day, year = map(int, m.groups())
    try:
        from datetime import date
        return date(year, month, day).isoformat()
    except ValueError:
        return None
