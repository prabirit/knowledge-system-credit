"""Product lists: credit cards, certificates, mobile wallets."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from contract import Answer, Source  # noqa: E402
from ..routing import all_of, has, none_of


def answer_product_list(question: str, target: str, store):
    """Return complete, domain-specific lists from the official product pages."""
    q = question.lower()
    pages = store.pages_by_snapshot.get(target, [])
    if ((has("credit_card_entity", q) or has("platinum_visa_entity", q) or has("rewards_visa_entity", q) or has("visa_rate_entity", q))
            and has("credit_card_rate_words", q)
            and none_of(q, "credit_card_list")):
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
                for row in store.rows_by_snapshot.get(target, []):
                    if row["url"] != page["url"]:
                        continue
                    card = row["cells"].get("Card Type", "")
                    apr = row["cells"].get("APR", "")
                    if card in ("Business Platinum Visa", "Business Rewards Visa") and apr:
                        cards.append((card, apr.rstrip("1") + " APR"))
                sources.append(Source(url=page["url"], snapshot_id=page["snapshot_id"], quote="Business Visa card rate table."))
        named = [c for c in cards if (("platinum" in q) == ("platinum" in c[0].lower()) or "platinum" not in q)
                 and (("rewards" in q) == ("rewards" in c[0].lower()) or "rewards" not in q)
                 and (("business" in q) == ("business" in c[0].lower()) or ("platinum" not in q and "rewards" not in q))]
        if ("platinum" in q or "rewards" in q) and named:
            cards = named
        if cards:
            text = "Credit card standard APRs: " + "; ".join("{}: {}".format(name, apr) for name, apr in cards)
            return Answer(text=text, sources=sources, confident=True)

    if has("certificate_subject", q) or (has("certificate_special_term", q) and has("month_term", q)):
        asks_for_link = has("certificate_link_words", q)
        if asks_for_link:
            target_page = next((p for p in pages if urlparse(p["url"]).path.lower().rstrip("/") == "/personal/savings-account"), None)
            if target_page:
                url = "https://www.dupaco.com/personal/savings-account#rates"
                return Answer(text=url, sources=[Source(url=url, snapshot_id=target_page["snapshot_id"], quote="See today's certificate rates on the savings account rates section.")], confident=True)
        if has("certificate_rate_words", q):
            rate_page = next((p for p in pages if urlparse(p["url"]).path.lower().rstrip("/") == "/rates"), None)
            if rate_page:
                rows = []
                seen = set()
                for row in store.rows_by_snapshot.get(target, []):
                    if row["url"] != rate_page["url"] or not row.get("cells"):
                        continue
                    cells = row["cells"]
                    product = next(iter(cells.values()), "")
                    low = product.lower()
                    is_cert = "certificate" in low or re.match(r"^\d+\s+months?$", low)
                    if not is_cert or "ira" in low or "roth" in low or "traditional" in low:
                        continue
                    apy = next((v for k, v in cells.items() if "apy" in k.lower() or "yield" in k.lower()), "")
                    rate = cells.get("Dividend Rate", "")
                    minimum = next((v for k, v in cells.items() if "min" in k.lower()), "")
                    if apy and product not in seen:
                        seen.add(product)
                        rows.append((product, rate, re.sub(r"(%)\d+$", r"\1", apy.strip()), minimum))
                # Narrow to the requested term / jumbo / special when the question names them.
                term_match = re.search(r"\b(\d{1,3})\s*[- ]?\s*(?:months?|mo)\b", q)
                if term_match:
                    term = term_match.group(1)
                    rows = [r for r in rows if re.match(r"^{}\s+months?\b".format(term), r[0].lower())]
                    if not rows:
                        return Answer("The website doesn't list a {}-month certificate rate. Please contact Dupaco.".format(term), confident=False)
                    if has("jumbo_qualifier", q):
                        rows = [r for r in rows if "jumbo" in r[0].lower()] or rows
                    else:
                        rows = [r for r in rows if "jumbo" not in r[0].lower()] or rows
                if rows:
                    text = "Current certificate rates: " if not term_match else "Certificate rate: "
                    text += "; ".join("{}: {} dividend rate, {} APY (minimum {})".format(n, r, a, m) for n, r, a, m in rows)
                    return Answer(text=text, sources=[Source(url=rate_page["url"], snapshot_id=rate_page["snapshot_id"], quote="Certificate rate tables.")], confident=True)

    if has("wallet_subject", q) or all_of(q, "wallet_card_subject"):
        page = next((p for p in pages if urlparse(p["url"]).path.lower().rstrip("/") == "/online-and-mobile-banking/mobile-payments"), None)
        if page:
            supported = [name for name in ("Apple Pay", "Google Pay", "Samsung Pay") if name.lower() in page["text"].lower()]
            if supported:
                text = "Yes. Dupaco debit and credit cards can be added to " + ", ".join(supported[:-1]) + (" and " if len(supported) > 1 else "") + (supported[-1] if supported else "") + "."
                return Answer(text=text, sources=[Source(url=page["url"], snapshot_id=page["snapshot_id"], quote=text)], confident=True)
    return None
