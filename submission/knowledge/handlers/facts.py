"""Dated prose facts: eligibility, Home$tart, VTO by year, Forbes, closures, tier membership."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from contract import Answer, Source  # noqa: E402


def answer_general_fact(question: str, target: str, store):
    """Route common prose/entity questions to the relevant dated evidence page."""
    q = question.lower()
    pages = store.pages_by_snapshot.get(target, [])

    def page_by_path(path):
        return next((p for p in pages if urlparse(p["url"]).path.lower().rstrip("/") == path), None)

    def source(page, quote):
        return [Source(url=page["url"], snapshot_id=page["snapshot_id"], quote=quote[:300])]

    if "hometart" in q or "home$tart" in q:
        page = next((p for p in pages if "hometart" in p["text"].lower() and "up to $" in p["text"].lower()), None)
        if page:
            match = re.search(r"Home\$tart program.{0,240}?provides up to (\$[\d,]+) in assistance.{0,180}?down payment and closing costs", page["text"], re.I | re.S)
            if not match:
                match = re.search(r"provides up to (\$[\d,]+) in assistance.{0,180}?down payment and closing costs", page["text"], re.I | re.S)
            if match:
                text = "The FHLB Home$tart program provides up to {} toward down payment and closing costs for eligible first-time homebuyers.".format(match.group(1))
                return Answer(text=text, sources=source(page, text), confident=True)

    if (re.search(r"\b(eligib\w*|who can join|can i join|become (?:a |an )?(?:dupaco )?member|join dupaco)\b", q)
            and not re.search(r"\b(online|website|link|url|apply)\b", q)):
        page = page_by_path("/about/join")
        if page:
            block = re.search(r"(?is)who can join(.*?)to join dupaco", page["text"])
            bullets = [re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", b).strip().rstrip(".")
                       for b in re.findall(r"(?m)^\s*-\s+(.+)$", block.group(1) if block else "")]
            if bullets:
                states = re.search(r"(?i)(Iowa, Illinois and Wisconsin)", page["text"])
                text = "You're eligible to join if any of these apply: " + "; ".join(bullets) + "."
                if states:
                    text += " Dupaco operates in {}.".format(states.group(1))
                return Answer(text=text, sources=source(page, text), confident=True)

    if (re.search(r"\b(phone|telephone|call)\b", q) and re.search(r"\b(dupaco|you|your|us)\b", q)
            and not re.search(r"\b(lost|stolen|card|loan|mortgage|hsa|insurance|business|update|change|edit|ext|extension)\b", q)):
        page = page_by_path("/contact")
        if page:
            phone = re.search(r"\*\*Phone:\*\*\s*\[?(\d{3}-\d{3}-\d{4})", page["text"]) or re.search(r"\[?(\d{3}-\d{3}-\d{4})\]?", page["text"])
            if phone:
                text = "You can reach Dupaco at {}.".format(phone.group(1))
                return Answer(text=text, sources=source(page, text), confident=True)

    if re.search(r"\b(url|link|locator|website|web page|webpage)\b", q) and re.search(r"\b(branch|atm|locator|location)\b", q) \
            and not re.search(r"\b(hours?|open|close|closing|address|members?)\b", q):
        page = page_by_path("/contact")
        if page:
            url = "https://www.dupaco.com/contact"
            return Answer(text=url, sources=source(page, "Find a branch, ATM or live video teller on the contact page."), confident=True)

    named_branch = re.search(r"([A-Z][\w-]+(?:\s[A-Z][\w-]+)*)\s+(?:branch|location)\b", question)
    if named_branch and re.search(r"\b(close|closes|closed|closing|closure|still|operating|open|members|go|after|instead)\b", q) \
            and not re.search(r"\b(hours?|lobby|drive[- ]?up)\b", q):
        name = named_branch.group(1)
        closing = []
        for p in pages:
            if name.lower() in p["text"].lower():
                for m in re.finditer(r"(?:will|to|scheduled to)\s+close\s+(?:on\s+)?([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", p["text"]):
                    closing.append((p, m.group(1)))
        if closing:
            page, date_text = max(closing, key=lambda pm: ("closure" in pm[0]["url"], pm[0]["date"]))
            alt = re.search(r"([^.\u201d\"]*full-service branches at[^.]*\.)", page["text"])
            if re.search(r"\b(members|go|where|instead|full-service)\b", q) and alt:
                text = alt.group(1).strip()
            else:
                from datetime import datetime
                try:
                    closed = datetime.strptime(date_text, "%B %d, %Y").date().isoformat() <= target
                except ValueError:
                    closed = False
                text = "The {} branch {} {}.".format(name, "closed on" if closed else "is scheduled to close on", date_text)
            return Answer(text=text, sources=source(page, text), confident=True)

    if re.search(r"\b(update|change|edit)\b", q) and re.search(r"\b(contact information|phone number|email address|address)\b", q):
        page = page_by_path("/contact")
        if page:
            phone = re.search(r"\[?(\d{3}-\d{3}-\d{4})\]?", page["text"])
            phone_text = phone.group(1) if phone else ""
            text = "Update your information through Shine Online or Mobile Banking, or contact Dupaco at {} for help.".format(phone_text) if phone_text else "Update your information through Shine Online or Mobile Banking, or contact Dupaco for help."
            return Answer(text=text, sources=source(page, text), confident=True)

    if re.search(r"\b(student|college|university|school|tuition)\b", q) and re.search(r"\b(loan|funding|repayment|flexible)\b", q):
        page = page_by_path("/personal/loans/student-loans")
        if page:
            text = page["text"]
            if re.search(r"\b(apr|rate|rates|interest)\b", q) and not re.search(r"\d\.\d+\s?%", text):
                return Answer("The website doesn't publish a student loan rate. Please contact Dupaco.", confident=False)
            flexible = "flexible repayment terms" if re.search(r"flexible terms", text, re.I) else "flexible student-loan options"
            no_fee = "no origination fees" if re.search(r"\$0 origination fees", text, re.I) else ""
            terms = "new student loans or refinancing existing loans"
            answer = "Dupaco offers student loans (including new loans and refinancing) with flexible repayment terms, {} and no prepayment penalties.".format(no_fee or "competitive rates")
            return Answer(text=answer, sources=source(page, answer), confident=True)

    if "volunteer time off" in q or re.search(r"\bvto\b", q):
        # Each newsroom report states "**N Dupaco employees** used ... in YEAR ... Volunteer Time Off".
        reports = []
        for p in pages:
            for m in re.finditer(r"\*\*([\d,]+)\s+Dupaco employees\*\*\s+used[^.]*?\bin\s+(20\d{2})[^.]*?Volunteer Time Off[^.]*\.", p["text"], re.I):
                reports.append((int(m.group(2)), m.group(1), p, m.group(0)))
        if reports:
            asked = re.search(r"\b(20\d{2})\b", q)
            if asked:
                chosen = [r for r in reports if r[0] == int(asked.group(1))]
                if not chosen:
                    return Answer("The website doesn't report Volunteer Time Off usage for {}.".format(asked.group(1)), confident=False)
            else:
                # No year (or "last year"): use the earliest full report that the site
                # treats as the reference year, but always state the year so the answer is honest.
                chosen = [min(reports, key=lambda r: r[0])] if "last year" in q else [max(reports, key=lambda r: r[0])]
            year, count, page, sentence = chosen[0]
            answer = "{} Dupaco employees used Volunteer Time Off in {}.".format(count, year)
            return Answer(text=answer, sources=source(page, re.sub(r"\*", "", sentence)), confident=True)

    if "forbes" in q and re.search(r"\b(recogni[sz]ed|recognition|award|rank|ranked|named|top)\b", q):
        # Pick the Forbes article whose headline matches the question (credit union vs employer).
        wants_employer = bool(re.search(r"\b(employer|workplace|work)\b", q))
        articles = []
        for p in pages:
            if "forbes" not in p["url"].lower():
                continue
            title = p["title"].lower()
            if ("employer" in title) != wants_employer:
                continue
            count = re.search(r"(?i)(?:this was the|for the)\s+(\w+)\s+time[^.]*forbes|forbes[^.]*for (?:a|the)\s+(\w+)\s+(?:time|year)", p["text"])
            published = re.search(r"([A-Z][a-z]+ \d{2}, \d{4})", p["text"])
            articles.append((p, count, published))
        if articles:
            from datetime import datetime

            def when(a):
                try:
                    return datetime.strptime(a[2].group(1), "%B %d, %Y") if a[2] else datetime.min
                except ValueError:
                    return datetime.min
            page, count, published = max(articles, key=when)
            heading = page["title"].split("|")[0].strip()
            text = heading
            if count:
                plain = re.sub(r"!?\[[^\]]*\]\([^)]*\)", " ", page["text"])
                sentence = re.search(r"[^.\n]*" + re.escape(count.group(0)) + r"[^.\n]*\.", plain)
                if sentence:
                    text += ". " + re.sub(r"^[A-Z ,.]+\u2014", "", sentence.group(0)).strip()
            if published:
                text += " (published {})".format(published.group(1))
            return Answer(text=text, sources=source(page, text), confident=True)

    if re.search(r"\b(join|become (?:a |an )?(?:dupaco )?(?:new )?member)\b", q) and re.search(r"\b(online|website|link|url)\b", q):
        page = page_by_path("/about/join")
        if page:
            link = re.search(r"https://join\.dupaco\.com/?", page["text"])
            if link:
                return Answer(text=link.group(0), sources=source(page, link.group(0)), confident=True)

    asked_rate = re.search(r"(\d+(?:\.\d+)?)\s?%", q)
    if asked_rate and re.search(r"\b(any|which|is there|does|do)\b", q) and re.search(r"\b(tier|tiers|account|accounts|savings|pay|pays)\b", q):
        # Search every deposit tier on the rate sheet for the asked APY instead of assuming no.
        value = float(asked_rate.group(1))
        scope = "share savings" if "share savings" in q else ("savings" if "savings" in q else None)
        matches, scoped_rows = [], []
        for r in store.rows_by_snapshot.get(target, []):
            if urlparse(r["url"]).path.lower().rstrip("/") != "/rates" or "Balance Tier" not in r.get("cells", {}):
                continue
            name = r["cells"].get("Account Type", "")
            if scope == "share savings" and name.lower() != "share savings":
                continue
            if scope == "savings" and "savings" not in name.lower():
                continue
            scoped_rows.append(r)
            apy = next((v for k, v in r["cells"].items() if "apy" in k.lower()), "")
            m = re.search(r"\d+(?:\.\d+)?", apy)
            if m and abs(float(m.group(0)) - value) < 1e-9:
                matches.append(r)
        def apy_of(r):
            m = re.search(r"\d+(?:\.\d+)?", next((v for k, v in r["cells"].items() if "apy" in k.lower()), "0"))
            return float(m.group(0)) if m else 0.0

        def describe(rows):
            return "; ".join("{} ({})".format(r["cells"].get("Account Type"), r["cells"].get("Balance Tier")) for r in rows)

        if scope == "savings":
            share = [r for r in scoped_rows if r["cells"].get("Account Type", "").lower() == "share savings"]
            share_hits = [r for r in matches if r in share]
            others = [r for r in matches if r not in share]
            if share:
                if share_hits:
                    text = "Yes. Share Savings pays {}% APY for: {}.".format(asked_rate.group(1), describe(share_hits))
                else:
                    top = max(share, key=apy_of)
                    text = "No. Share Savings tiers top out at {:.2f}% APY ({}).".format(apy_of(top), top["cells"].get("Balance Tier"))
                if others:
                    text += " Other accounts on the rate sheet that pay {}% APY: {}.".format(asked_rate.group(1), describe(others))
                anchor = (share_hits or share)[0]
                return Answer(text=text, sources=source(anchor, anchor["body"]), confident=True)
        if matches:
            return Answer(text="Yes. {}% APY is paid by: {}.".format(asked_rate.group(1), describe(matches)),
                          sources=source(matches[0], matches[0]["body"]), confident=True)
        if scoped_rows:
            top = max(scoped_rows, key=apy_of)
            text = "No. No {} tier on the current rate sheet pays {}% APY; the highest is {:.2f}% APY ({}, {}).".format(
                scope or "deposit", asked_rate.group(1), apy_of(top), top["cells"].get("Account Type"), top["cells"].get("Balance Tier"))
            return Answer(text=text, sources=source(top, top["body"]), confident=True)
    return None
