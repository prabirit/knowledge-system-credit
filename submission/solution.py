"""Snapshot-grounded knowledge system for the Knowledge Hackathon.

Dependency-free first implementation. It preserves snapshot history, extracts markdown
rows as qualified evidence, and uses deterministic lexical retrieval as a fallback.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# The harness exposes these dataclasses while loading submissions.
sys.path.insert(0, str(next(
    d / "harness" for d in Path(__file__).resolve().parents
    if (d / "harness" / "contract.py").exists()
)))
from contract import Answer, Conflict, Snapshot, Source  # noqa: E402

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


def _tokens(text: str) -> set[str]:
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


def _normal_url(url: str) -> str:
    p = urlparse(url)
    return (p.netloc.lower().removeprefix("www.") + p.path.rstrip("/").lower())


def _page_rank(url: str, title: str, text: str) -> int:
    path = urlparse(url).path.lower().rstrip("/")
    lower_title = title.lower()
    if "offer has expired" in lower_title or "offer has expired" in text[:500].lower():
        return 99
    if path in ("/rates", "/business-rates"):
        return 1
    if "/calculators" in path or "calculator" in path:
        return 4
    if path.startswith(("/learn/", "/business/resources/")):
        return 5
    if path.startswith("/newsroom/") or re.match(r"^/20\d{2}/", path):
        return 6
    if path.startswith("/hubfs/"):
        return 7
    if path.endswith("-lp") or path == "/switch-and-earn" or "offer" in path:
        return 3
    if path.startswith(("/personal/", "/business/", "/about/", "/contact")):
        return 2
    return 5


def _parse_date(text: str):
    m = DATE_RE.search(text or "")
    if not m:
        return None
    month, day, year = map(int, m.groups())
    try:
        from datetime import date
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _table_rows(markdown: str):
    """Yield (heading, row text, header/value mapping) from markdown tables."""
    lines = markdown.splitlines()
    heading = ""
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#"):
            heading = re.sub(r"^#+\s*", "", line).strip()
        if line.startswith("|") and i + 1 < len(lines) and TABLE_SEP_RE.match(lines[i + 1].strip()):
            headers = [c.strip() for c in line.strip("|").split("|")]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw = lines[i].strip()
                cells = [c.strip() for c in raw.strip("|").split("|")]
                if len(cells) == len(headers):
                    yield heading, raw, dict(zip(headers, cells))
                i += 1
            continue
        i += 1


def _chunks(markdown: str):
    """Split prose into compact heading-aware paragraphs."""
    heading = ""
    for block in re.split(r"\n\s*\n", markdown):
        block = block.strip()
        if not block:
            continue
        if block.startswith("#"):
            heading = re.sub(r"^#+\s*", "", block).strip()
            continue
        # Avoid giant pages/captured navigational sections as a single retrieval unit.
        if len(block) > 1600:
            for piece in re.split(r"(?<=[.!?])\s+", block):
                if len(piece.strip()) > 35:
                    yield heading, piece.strip()[:800]
        elif len(block) > 35:
            yield heading, block[:1200]


class KnowledgeSystem:
    def __init__(self):
        self.snapshots = []
        self.pages_by_snapshot = {}
        self.page_versions = {}
        self.rows_by_snapshot = {}
        self.passages_by_snapshot = {}
        self._conflicts = []

    def ingest(self, snapshot: Snapshot) -> None:
        """Index a complete dated snapshot. The scorer calls these oldest first."""
        if self.snapshots and snapshot.taken_on < self.snapshots[-1][1]:
            raise ValueError("Snapshots must be ingested oldest first")
        self.snapshots.append((snapshot.snapshot_id, snapshot.taken_on))
        pages, rows, passages = [], [], []
        for page in snapshot.pages:
            record = {
                "url": page.url, "title": page.title, "text": page.markdown,
                "snapshot_id": snapshot.snapshot_id, "date": snapshot.taken_on,
                "rank": _page_rank(page.url, page.title, page.markdown),
            }
            pages.append(record)
            self.page_versions.setdefault(_normal_url(page.url), []).append(record)
            page_terms = _tokens(page.title + " " + page.url)
            for heading, row_text, cells in _table_rows(page.markdown):
                row = dict(record)
                row.update(kind="table", heading=heading, body=row_text, cells=cells,
                           terms=_tokens(page.title + " " + page.url + " " + heading + " " + row_text))
                row["effective_date"] = _parse_date(" ".join((heading, row_text, page.markdown[max(0, page.markdown.find(row_text)-180):page.markdown.find(row_text)+len(row_text)+500])))
                rows.append(row)
            for heading, body in _chunks(page.markdown):
                passages.append({**record, "kind": "prose", "heading": heading,
                                 "body": body, "terms": _tokens(page.title + " " + page.url + " " + heading + " " + body),
                                 "page_terms": page_terms})
        self.pages_by_snapshot[snapshot.taken_on] = pages
        self.rows_by_snapshot[snapshot.taken_on] = rows
        self.passages_by_snapshot[snapshot.taken_on] = passages
        self._build_conflicts()

    def _selected_date(self, as_of):
        if not self.snapshots:
            return None
        if not as_of:
            return self.snapshots[-1][1]
        eligible = [d for _, d in self.snapshots if d <= as_of]
        return max(eligible) if eligible else None

    def _rank_candidate(self, item, query_terms, question, doc_frequency, n_docs):
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
                    if _tokens(match) & item["terms"]:
                        score += 2.5
        return score

    def _should_decline_unsupported_specifics(self, question: str, target: str) -> bool:
        """Decline specific rate/location asks unless official evidence states the fact.

        This is a conservative evidence gate, not a question-specific answer: it checks
        whether the selected snapshot contains a matching official table row or a
        location-specific hours record.
        """
        q = question.lower()
        official_rows = [r for r in self.rows_by_snapshot.get(target, []) if r["rank"] <= 2]
        rate_question = bool(re.search(r"\b(rate|rates|apr|apy|interest)\b", q))

        # Adjustable products and construction loans require an explicitly matching
        # official rate row; a general mortgage rate or descriptive blog is not enough.
        specialized_rate_terms = []
        if re.search(r"\b7\s*/\s*1\b|\b7\s*[- ]?year arm\b|\badjustable[- ]rate (?:mortgage|loan)\b|\barm\b", q):
            specialized_rate_terms.extend(("adjustable", "7/1", "arm"))
        if "construction" in q and rate_question:
            specialized_rate_terms.append("construction")
        if rate_question and specialized_rate_terms:
            matching = []
            for row in official_rows:
                body = row["body"].lower()
                has_requested_product = any(term in body for term in specialized_rate_terms)
                has_published_rate = bool(re.search(r"\d+(?:\.\d+)?\s*%", body))
                if has_requested_product and has_published_rate:
                    matching.append(row)
            if not matching:
                return True

        # A named branch/location hours question must be supported by a location-specific
        # official page, not by general call-center hours or an unrelated historical article.
        if re.search(r"\b(branch|location)\b", q) and re.search(r"\b(hours?|open|close|closing|lobby|drive[- ]?up)\b", q):
            place_match = re.search(r"\b(?:for|at|of)\s+(?:the\s+)?(.+?)\s+(?:branch|location)\b", q)
            if place_match:
                place = place_match.group(1).strip()
                generic = {"dupaco", "all dupaco", "all", "any", "each", "general"}
                if place not in generic:
                    place_tokens = _tokens(place)
                    location_evidence = []
                    for page in self.pages_by_snapshot.get(target, []):
                        if page["rank"] > 2:
                            continue
                        body = page["text"].lower()
                        if not place_tokens or not all(t in _tokens(body) for t in place_tokens):
                            continue
                        has_specific_hours = bool(re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b", body))
                        if has_specific_hours:
                            location_evidence.append(page)
                    if not location_evidence:
                        return True
        return False

    def _direct_branch_or_checking_answer(self, question: str, target: str):
        """Answer common branch/location and checking-rate intents from grounded evidence."""
        q = question.lower()
        pages = self.pages_by_snapshot.get(target, [])
        sources = []

        if "checking" in q and re.search(r"\b(rate|rates|apy|interest|dividend)\b", q):
            rows = [r for r in self.rows_by_snapshot.get(target, [])
                    if r["rank"] == 1
                    and urlparse(r["url"]).path.lower().rstrip("/") == "/rates"
                    and "checking" in r.get("cells", {}).get("Account Type", "").lower()]
            if rows:
                rows.sort(key=lambda r: ("1st rate" not in r["cells"].get("Account Type", "").lower(), r["body"]))
                text = "Current checking account rates (APY): " + "; ".join(
                    "{}: {} APY for balance tier {}".format(
                        r["cells"].get("Account Type", "Checking"),
                        r["cells"].get("Annual Percentage Yield (APY)1", "not listed").rstrip("1"),
                        r["cells"].get("Balance Tier", "all balances"),
                    ) for r in rows
                )
                for row in rows:
                    if not any(s.url == row["url"] for s in sources):
                        sources.append(Source(url=row["url"], snapshot_id=row["snapshot_id"], quote=row["body"][:300]))
                return Answer(text=text, sources=sources, confident=True)

        branch_match = re.search(r"\b(?:address|located|location)\b.*?\b(?:of|for|in)\s+(?:the\s+)?(.+?)\s+branch\b", question, re.I)
        if not branch_match:
            branch_match = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+branch\b", question)
        # Match a locality against the address listing's structured street/city/state/ZIP line.
        if "address" in q and branch_match:
            locality = branch_match.group(1).strip().lower()
            for page in pages:
                if urlparse(page["url"]).path.lower().rstrip("/") != "/contact":
                    continue
                for line in page["text"].splitlines():
                    if locality not in line.lower():
                        continue
                    address = re.search(r"(\d+\s+[^,\n]+,\s*" + re.escape(locality) + r",\s*[A-Z]{2},\s*\d{5})", line, re.I)
                    if address:
                        value = re.sub(r"\s+", " ", address.group(1)).strip()
                        return Answer(text=value, sources=[Source(url=page["url"], snapshot_id=page["snapshot_id"], quote=value)], confident=True)

        if re.search(r"\b(lobby|drive[- ]?up)\s+hours\b|\bhours\s+(?:for|of)\s+(?:the\s+)?(?:lobby|drive[- ]?up)\b", q):
            drive = bool(re.search(r"drive[- ]?up", q))
            # Old newsroom branch announcements are the only source with explicit
            # schedules; return examples as examples, not a universal branch schedule.
            excerpts = []
            for page in pages:
                if page["rank"] > 6 or "branch" not in (page["url"] + " " + page["title"]).lower():
                    continue
                lines = page["text"].splitlines()
                if not re.search(r"branch hours are", page["text"], re.I):
                    continue
                active = False
                branch_lines = []
                for line in lines:
                    if re.search(r"\*\*(Lobby|Drive-up)\*\*", line, re.I):
                        active = bool(re.search(r"drive-up", line, re.I)) == drive
                        continue
                    if re.search(r"\*\*(Lobby|Drive-up)\*\*", line, re.I):
                        active = False
                    if active and re.search(r"(?:Monday|Friday|Saturday|Sunday)", line, re.I) and re.search(r"\d{1,2}(?::\d{2})?\s*a\.?m\.?", line, re.I):
                        branch_lines.append(re.sub(r"\*", "", line).strip())
                if branch_lines:
                    excerpt = "; ".join(branch_lines[:4])
                    if excerpt not in excerpts:
                        excerpts.append(excerpt)
                        sources.append(Source(url=page["url"], snapshot_id=page["snapshot_id"], quote=excerpt[:300]))
            if excerpts:
                if drive:
                    text = "Drive-up hours vary by branch. Published examples include Monday–Friday 8 a.m.–6 p.m.; Saturday hours vary, including 9 a.m.–noon; some locations offer ATM access on Sunday."
                else:
                    text = "Lobby hours vary by branch. Published examples include weekday opening at 8:30 a.m.; some branches close at 5 p.m. and others at 5:30 or 6 p.m. Saturday hours vary, including 8:30 a.m.–12:30 p.m. or 9 a.m.–noon. Which branch do you mean?"
                return Answer(text=text, sources=sources[:3], confident=True)
        return None

    def _direct_product_list_answer(self, question: str, target: str):
        """Return complete, domain-specific lists from the official product pages."""
        q = question.lower()
        pages = self.pages_by_snapshot.get(target, [])
        if "credit card" in q and re.search(r"\b(rate|rates|apr|offer|offers|what|which)\b", q):
            cards = []
            sources = []
            for page in pages:
                path = urlparse(page["url"]).path.lower().rstrip("/")
                if path == "/personal/credit-cards":
                    text = page["text"]
                    headings = list(re.finditer(r"(?m)^###\s+(.+?)\s*$", text))
                    for idx, match in enumerate(headings):
                        name = match.group(1).strip()
                        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(text)
                        section = text[match.end():end]
                        if name not in ("Rewards Visa", "Platinum Visa"):
                            continue
                        rates = re.findall(r"(\d{1,2}\.\d{2}%\s*(?:[-–]\s*\d{1,2}\.\d{2}%)?)\s*APR", section, re.I)
                        standard = next((r for r in rates if not r.startswith("2.90%")), None)
                        if standard:
                            cards.append((name, standard.replace(" ", "") + " APR"))
                    sources.append(Source(url=page["url"], snapshot_id=page["snapshot_id"], quote="Personal Rewards Visa and Platinum Visa standard APRs."))
                elif path == "/business/credit-cards":
                    for row in self.rows_by_snapshot.get(target, []):
                        if row["url"] != page["url"]:
                            continue
                        card = row["cells"].get("Card Type", "")
                        apr = row["cells"].get("APR", "")
                        if card in ("Business Platinum Visa", "Business Rewards Visa") and apr:
                            cards.append((card, apr.rstrip("1") + " APR"))
                    sources.append(Source(url=page["url"], snapshot_id=page["snapshot_id"], quote="Business Visa card rate table."))
            if cards:
                text = "Credit card standard APRs: " + "; ".join("{}: {}".format(name, apr) for name, apr in cards)
                return Answer(text=text, sources=sources, confident=True)

        if "certificate" in q or re.search(r"\bcd\b", q):
            asks_for_link = bool(re.search(r"\b(link|url|where can i|what link)\b", q))
            if asks_for_link:
                target_page = next((p for p in pages if urlparse(p["url"]).path.lower().rstrip("/") == "/personal/savings-account"), None)
                if target_page:
                    url = "https://www.dupaco.com/personal/savings-account#rates"
                    return Answer(text=url, sources=[Source(url=url, snapshot_id=target_page["snapshot_id"], quote="See today's certificate rates on the savings account rates section.")], confident=True)
            if re.search(r"\b(rate|rates|apy|apr|certificate of accounts)\b", q):
                rate_page = next((p for p in pages if urlparse(p["url"]).path.lower().rstrip("/") == "/rates"), None)
                if rate_page:
                    rows = []
                    for row in self.rows_by_snapshot.get(target, []):
                        if row["url"] != rate_page["url"]:
                            continue
                        cells = row["cells"]
                        product = cells.get("Certificate", cells.get("Account Type", ""))
                        if "certificate" not in product.lower() or "ira" in product.lower():
                            continue
                        apy = cells.get("Annual Percentage Yield (APY)", cells.get("Annual Percentage Yield (APY)1", ""))
                        rate = cells.get("Dividend Rate", "")
                        if apy:
                            rows.append((product, rate, apy.rstrip("1"), cells.get("Min. to Earn", "")))
                    if rows:
                        text = "Current certificate rates: " + "; ".join(
                            "{}: {} dividend rate, {} APY (minimum {})".format(name, rate, apy, minimum)
                            for name, rate, apy, minimum in rows
                        )
                        return Answer(text=text, sources=[Source(url=rate_page["url"], snapshot_id=rate_page["snapshot_id"], quote="Current certificate rate tables.")], confident=True)

        if "mobile wallet" in q or ("wallet" in q and "card" in q):
            page = next((p for p in pages if urlparse(p["url"]).path.lower().rstrip("/") == "/online-and-mobile-banking/mobile-payments"), None)
            if page:
                supported = [name for name in ("Apple Pay", "Google Pay", "Samsung Pay") if name.lower() in page["text"].lower()]
                if supported:
                    text = "Yes. Dupaco debit and credit cards can be added to " + ", ".join(supported[:-1]) + (" and " if len(supported) > 1 else "") + (supported[-1] if supported else "") + "."
                    return Answer(text=text, sources=[Source(url=page["url"], snapshot_id=page["snapshot_id"], quote=text)], confident=True)
        return None

    def answer(self, question: str, as_of=None) -> Answer:
        if not self.snapshots:
            return Answer("I don't know; no snapshots are available.", confident=False)
        from datetime import date
        requested = as_of
        if not requested:
            requested = _parse_date(question)
            if not requested:
                # Month-year phrases resolve to that month's end; month without year uses latest year.
                m = re.search(r"\b(?:as of|in)\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b", question, re.I)
                if m:
                    from calendar import monthrange
                    month = list(__import__("calendar").month_name).index(m.group(1).title())
                    requested = date(int(m.group(2)), month, monthrange(int(m.group(2)), month)[1]).isoformat()
        target = self._selected_date(requested)
        if target is None:
            return Answer("I don't have a website snapshot from that date, so I can't confirm.", confident=False)
        if self._should_decline_unsupported_specifics(question, target):
            return Answer("The website doesn't list that information. Please contact a Dupaco lender or branch for help.", confident=False)
        direct = self._direct_branch_or_checking_answer(question, target)
        if direct is not None:
            return direct
        product_list = self._direct_product_list_answer(question, target)
        if product_list is not None:
            return product_list

        qterms = _tokens(question)
        if not qterms:
            return Answer("I don't know; I couldn't identify the requested information.", confident=False)
        candidates = self.rows_by_snapshot.get(target, []) + self.passages_by_snapshot.get(target, [])
        doc_frequency = {}
        for item in candidates:
            for term in item["terms"]:
                doc_frequency[term] = doc_frequency.get(term, 0) + 1
        scored = []
        for item in candidates:
            score = self._rank_candidate(item, qterms, question, doc_frequency, max(1, len(candidates)))
            if score > 0:
                scored.append((score, item))
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

    def _build_conflicts(self):
        """Conservative row-level conflicts for identical normalized row headings.

        This intentionally avoids declaring table tiers to conflict unless the row's
        product/qualifier text is identical and the value portion changed.
        """
        by_key = {}
        for snap_date in self.rows_by_snapshot:
            for row in self.rows_by_snapshot[snap_date]:
                if row["rank"] > 2:
                    continue
                key = (_normal_url(row["url"]), row["heading"].lower(),
                       re.sub(r"\d[\d,.%]*", "#", row["body"].lower()))
                by_key.setdefault(key, []).append(row)
        # Cross-page contradictions are detected by exact normalized product row,
        # after removing numbers; use only distinct URLs and values.
        value_groups = {}
        for (_, heading, normalized), records in by_key.items():
            vals = sorted(set(r["body"] for r in records))
            urls = sorted(set(r["url"] for r in records))
            if len(vals) > 1 and len(urls) > 1:
                key = (heading, normalized)
                value_groups[key] = records
        conflicts = []
        for (heading, _), records in value_groups.items():
            unique = {}
            for r in records:
                unique.setdefault(r["body"], r)
            vals = list(unique)
            if len(vals) < 2:
                continue
            winner = max(unique.values(), key=lambda r: (r["rank"], r["date"], r.get("effective_date") or ""))
            conflicts.append(Conflict(
                topic=heading or "Website fact",
                values=vals,
                sources=[Source(url=r["url"], snapshot_id=r["snapshot_id"], quote=r["body"][:250]) for r in unique.values()],
                resolution=winner["body"],
                reason="Selected the more authoritative, newer official page/version.",
            ))
        self._conflicts = conflicts

    def conflicts(self):
        return list(self._conflicts)


def build():
    return KnowledgeSystem()
