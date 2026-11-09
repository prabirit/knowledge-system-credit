"""Rate lookups: personal-loan APR by term, deposit APY by named product and balance tier."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from contract import Answer, Source  # noqa: E402
from ..routing import all_of, has


def answer_rate_lookup(question: str, target: str, store):
    """Look up (a) personal-loan APR by term and (b) a named deposit product, choosing the
    balance tier that contains any dollar amount in the question."""
    q = question.lower()
    qn = re.sub(r"[\u2019']", "", q).replace("-", " ")
    rate_words = has("named_rate_words", q)
    rows = store.rows_by_snapshot.get(target, [])

    # (a) personal loan APR by term
    term = re.search(r"\b(\d{1,3})\s*[- ]?\s*months?\b", q)
    if has("personal_loan_subject", q) and term and rate_words:
        wanted = int(term.group(1))
        for row in rows:
            if urlparse(row["url"]).path.lower().rstrip("/") != "/personal/loans/personal-loans" or not row.get("cells"):
                continue
            cells = list(row["cells"].values())
            if re.fullmatch(r"{}\s+months?".format(wanted), cells[0].strip(), re.I) and len(cells) > 1:
                apr = re.search(r"\d+(?:\.\d+)?\s?%", cells[1])
                if apr:
                    text = "Personal loan APR for a {}-month term: {} APR (as low as, based on credit qualification).".format(wanted, apr.group(0).replace(" ", ""))
                    return Answer(text=text, sources=[Source(url=row["url"], snapshot_id=row["snapshot_id"], quote=row["body"][:200])], confident=True)
        return Answer("The website doesn't list a personal loan rate for a {}-month term. Please contact Dupaco.".format(wanted), confident=False)

    # (b) named deposit product on the consumer rate sheet
    if not rate_words or has("business_context", q):
        return None
    products = {}
    for row in rows:
        if urlparse(row["url"]).path.lower().rstrip("/") != "/rates" or not row.get("cells"):
            continue
        cells = row["cells"]
        name = cells.get("Account Type")
        if not name or "Balance Tier" not in cells:
            continue
        low = re.sub(r"[\u2019']", "", name.lower()).replace("-", " ")
        if re.search(r"certificate|\bira\b|roth|traditional|^\d+\s*month", low):
            continue
        products.setdefault(low, (name, []))[1].append(row)
    named = [(low, v) for low, v in products.items() if low in qn]
    if not named:
        return None
    low, (name, prows) = max(named, key=lambda kv: len(kv[0]))

    def tier_bounds(cell):
        nums = [float(x.replace(",", "")) for x in re.findall(r"\$\s?([\d,]+(?:\.\d+)?)", cell)]
        if not nums:
            return None
        if "+" in cell or len(nums) == 1:
            return (nums[0], float("inf"))
        return (nums[0], nums[1])

    amounts = [float(a.replace(",", "")) for a in re.findall(r"\$\s?([\d,]+(?:\.\d+)?)", q)]
    chosen = None
    if amounts:
        hit_rows = []
        for amount in amounts:
            match = [r for r in prows if (b := tier_bounds(r["cells"].get("Balance Tier", ""))) and b[0] <= amount <= b[1]]
            hit_rows.append(match[0] if match else None)
        if hit_rows and all(h is not None and h is hit_rows[0] for h in hit_rows):
            chosen = hit_rows[0]
        else:
            return None
    elif len(prows) == 1:
        chosen = prows[0]
    elif re.search(r"\b(highest|top|maximum|best)\b", q):
        def apy_of(r):
            m = re.search(r"\d+(?:\.\d+)?", next((v for k, v in r["cells"].items() if "apy" in k.lower()), "0"))
            return float(m.group(0)) if m else 0.0
        chosen = max(prows, key=apy_of)
    else:
        return None
    cells = chosen["cells"]
    apy = next((v for k, v in cells.items() if "apy" in k.lower()), "")
    dividend = cells.get("Dividend Rate", "")
    clean = lambda v: re.sub(r"(%)\d+$", r"\1", (v or "").strip())
    tier = cells.get("Balance Tier", "")
    if has("dividend_attribute", q):
        text = "{} dividend rate for balances of {}: {}.".format(name, tier, clean(dividend))
    else:
        text = "{} APY for balances of {}: {}.".format(name, tier, clean(apy))
    return Answer(text=text, sources=[Source(url=chosen["url"], snapshot_id=chosen["snapshot_id"], quote=chosen["body"][:250])], confident=True)
