"""Branches and checking: checking rates, branch/ATM addresses, lobby and drive-up hours."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from contract import Answer, Source  # noqa: E402
from ..routing import all_of, has


def answer_branch_or_checking(question: str, target: str, store):
    """Answer common branch/location and checking-rate intents from grounded evidence."""
    q = question.lower()
    pages = store.pages_by_snapshot.get(target, [])
    sources = []

    if has("checking_subject", q) and has("checking_rate_words", q):
        rows = [r for r in store.rows_by_snapshot.get(target, [])
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

    # Branch / ATM street address: match a city or street name from the structured
    # location listing on the contact page against the question.
    if all_of(q, "address_words", "branch_address_entity"):
        wants_atm = has("atm_entity", q)
        for page in pages:
            if urlparse(page["url"]).path.lower().rstrip("/") != "/contact":
                continue
            lines = page["text"].splitlines()
            entries = []
            for i, line in enumerate(lines):
                m = re.match(r"^(\d+\s+([^,]+)),\s*([^,]+),\s*([A-Z]{2}),\s*(\d{5})\s*$", line.strip())
                if not m:
                    continue
                label = " ".join(l.strip() for l in lines[max(0, i - 3):i] if l.strip())
                is_atm = "atm" in label.lower() and "branch" not in label.lower()
                street_name = re.sub(r"\s+(?:st|street|ave|avenue|rd|road|dr|drive|ln|lane|blvd|way|ct|pkwy)\.?$", "", m.group(2).strip(), flags=re.I)
                entries.append({"full": "{}, {}, {} {}".format(m.group(1).strip(), m.group(3).strip(), m.group(4), m.group(5)),
                                "city": m.group(3).strip().lower(), "street": street_name.lower(), "atm": is_atm})
            street_hits = [e for e in entries if e["street"] and re.search(r"\b{}\b".format(re.escape(e["street"])), q) and (wants_atm or not e["atm"])]
            city_hits = [e for e in entries if re.search(r"\b{}\b".format(re.escape(e["city"])), q) and (wants_atm or not e["atm"])]
            hits = street_hits or city_hits
            if hits:
                value = "; ".join(sorted({e["full"] for e in hits}))
                return Answer(text=value, sources=[Source(url=page["url"], snapshot_id=page["snapshot_id"], quote=value[:250])], confident=True)

    if has("hours_words", q):
        drive = has("drive_up", q)
        # Old newsroom branch announcements are the only source with explicit
        # schedules; return examples as examples, not a universal branch schedule.
        excerpts = []
        for page in pages:
            if page["rank"] > 6:
                continue
            lines = page["text"].splitlines()
            if not re.search(r"branch hours are", page["text"], re.I):
                continue
            active = False
            branch_lines = []
            for line in lines:
                label = re.search(r"\*\*(Lobby|Drive-up)\*\*", line, re.I)
                if label:
                    active = bool(re.search(r"drive-up", line, re.I)) == drive
                    line = line[label.end():]
                    if not line.strip():
                        continue
                if active and re.search(r"(?:Monday|Friday|Saturday|Sunday)", line, re.I) and re.search(r"\d{1,2}(?::\d{2})?\s*a\.?m\.?", line, re.I):
                    branch_lines.append(re.sub(r"\*", "", line).strip())
            if branch_lines:
                excerpt = "; ".join(branch_lines[:4])
                if excerpt not in excerpts:
                    excerpts.append(excerpt)
                    sources.append(Source(url=page["url"], snapshot_id=page["snapshot_id"], quote=excerpt[:300]))
        if excerpts:
            kind = "Drive-up" if drive else "Lobby"
            shown = excerpts[:6]
            text = ("{} hours vary by branch; the site publishes them per branch rather than one schedule. "
                    "Published examples: {}. Which branch do you mean?").format(kind, " | ".join(shown))
            return Answer(text=text, sources=sources[:6], confident=True)
    return None
