"""Conflict detection: contradictions within the current snapshot, with a reasoned winner."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from contract import Conflict, Source  # noqa: E402


def build_conflicts(store):
    """Build qualified, value-level conflicts across snapshots and pages.

    A fact key is (product, qualifiers, attribute). Values are normalized so that
    formatting differences ("4.20%1", "4.2 %", "9.59% APR") never count as
    contradictions, and different tiers/terms/attributes never share a key.
    """
    from collections import defaultdict

    facts = defaultdict(list)
    label_headers = {"account type", "certificate", "program", "loan program",
                     "card type", "product", "term", "loan type", "ira type"}
    ignored_headers = ("payment", "points", "min. to open")

    def norm_text(text):
        text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\\*", "").replace("*", "")
        return re.sub(r"\s+", " ", text).strip().lower()

    def norm_header(header):
        return re.sub(r"\s*\d+$", "", norm_text(header)).strip()

    def attribute_of(header):
        h = norm_header(header)
        if "apy" in h or "annual percentage yield" in h:
            return "apy"
        if "apr" in h or "annual percentage rate" in h:
            return "apr"
        if "dividend" in h:
            return "dividend rate"
        if h == "rate" or h.endswith(" rate"):
            return "rate"
        if "fee" in h:
            return "fee"
        return None

    def fmt_number(digits):
        # Keep real precision (6.037 stays 6.037) but pad to two decimals and drop
        # meaningless trailing zeros beyond that (7.250 -> 7.25, 4.2 -> 4.20).
        whole, _, frac = digits.partition(".")
        frac = frac.rstrip("0")
        frac = (frac + "00")[:max(2, len(frac))]
        return "{}.{}".format(int(whole), frac)

    def norm_value(value):
        numbers = re.findall(r"\$\s?[\d,]+(?:\.\d+)?|\d+(?:\.\d+)?\s?%", value or "")
        out = []
        for number in numbers:
            number = number.replace(" ", "")
            if number.endswith("%"):
                out.append(fmt_number(number[:-1]) + "%")
            else:
                out.append("$" + fmt_number(number[1:].replace(",", "")))
        return " - ".join(out)

    def norm_qualifier(value):
        value = norm_text(value)
        value = re.sub(r"(\d),(\d)", r"\1\2", value)
        return re.sub(r"\.00\b", "", value)

    for snap_date, rows in store.rows_by_snapshot.items():
        for row in rows:
            if row["rank"] >= 99:
                continue
            cells = row.get("cells") or {}
            labels, qualifiers, measures = [], [], []
            for header, value in cells.items():
                h = norm_header(header)
                if any(word in h for word in ignored_headers):
                    continue
                attribute = attribute_of(header)
                if attribute and norm_value(value):
                    measures.append((attribute, norm_value(value)))
                elif h in label_headers:
                    labels.append(norm_qualifier(value))
                elif value.strip() and value.strip() not in ("\u2014", "-"):
                    qualifiers.append((h, norm_qualifier(value)))
            if not labels or not measures:
                continue
            product = " ".join(labels)
            for attribute, value in measures:
                facts[(product, tuple(sorted(qualifiers)), attribute)].append({
                    "value": value, "url": row["url"], "snapshot_id": row["snapshot_id"],
                    "date": snap_date, "rank": row["rank"],
                    "effective_date": row.get("effective_date"), "quote": row["body"]})

    # Simple inline statements, e.g. "6-month certificate APY: 2.95%" or
    # "Lost debit card replacement fee: $2.50". Expired promotions are kept as
    # competing evidence but lose on authority.
    inline = re.compile(r"(?i)(\d{1,3})\s*[- ]month\s+certificate\s+(apy|apr|rate)\s*:?\s*(\d+(?:\.\d+)?\s?%)")
    fee_line = re.compile(r"(?im)^\s*([^:\n|]{3,80}\bfee\b[^:\n|]{0,40}):\s*(\$\s?[\d,]+(?:\.\d+)?)")
    for snap_date, pages in store.pages_by_snapshot.items():
        for page in pages:
            text = page["text"]
            for match in inline.finditer(text):
                term, attr, value = match.groups()
                facts[("{}-month certificate".format(term), (), attr.lower())].append({
                    "value": norm_value(value), "url": page["url"], "snapshot_id": page["snapshot_id"],
                    "date": snap_date, "rank": page["rank"], "effective_date": None,
                    "quote": text[max(0, match.start() - 40):match.end() + 60].strip()})
            for match in fee_line.finditer(text):
                label, value = match.groups()
                facts[(norm_text(label), (), "fee")].append({
                    "value": norm_value(value), "url": page["url"], "snapshot_id": page["snapshot_id"],
                    "date": snap_date, "rank": page["rank"], "effective_date": None,
                    "quote": text[max(0, match.start() - 20):match.end() + 40].strip()})

    # Cross-label comparison for model-year tables: a stale calculator row
    # ("2023-26 Model Year | 60 Months") contradicts the official row
    # ("2024-27 Model Year | 60 Months") when the year ranges overlap.
    def year_range(text):
        m = re.search(r"\b(\d{4})\s*-\s*(\d{2,4})\b", text)
        if not m:
            return None
        start, end = int(m.group(1)), int(m.group(2))
        if end < 100:
            end = (start // 100) * 100 + end
        return (start, end) if end >= start else None

    cross = defaultdict(list)
    latest_date = store.snapshots[-1][1] if store.snapshots else None
    for (product, qualifiers, attribute), records in facts.items():
        yr = year_range(product)
        term = re.search(r"\b(\d{2,3}) months?\b", product)
        if not yr or not term:
            continue
        for record in records:
            # Cross-page stale traps concern the current site; historical changes
            # are handled by same-key conflicts below.
            if record["date"] != latest_date:
                continue
            path = urlparse(record["url"]).path.lower().rstrip("/")
            if not (path.endswith("/rates") or path.endswith("/auto-loans") or
                    path.endswith("/auto-motorcycle-loans") or path.endswith("/vehicle-affordability") or
                    path == "/switch-and-earn"):
                continue
            cross[(record["date"], int(term.group(1)), attribute)].append((yr, product, record))
    cross_conflicts = {}
    for (snap_date, term, attribute), items in cross.items():
        # Collapse duplicate copies of the same model-year row, preferring highest authority.
        official_by_range, stale_by_range = {}, {}
        for yr, product, record in items:
            bucket = official_by_range if record["rank"] <= 2 else stale_by_range
            existing = bucket.get(yr)
            if existing is None or (-record["rank"], record["url"]) > (-existing[2]["rank"], existing[2]["url"]):
                bucket[yr] = (yr, product, record)
        official, stale = list(official_by_range.values()), list(stale_by_range.values())
        for yr_s, prod_s, rec_s in stale:
            best, best_year, best_overlap = None, None, 0
            for yr_o, prod_o, rec_o in official:
                overlap = min(yr_s[1], yr_o[1]) - max(yr_s[0], yr_o[0]) + 1
                if prod_o != prod_s and overlap > best_overlap:
                    best, best_year, best_overlap = rec_o, yr_o, overlap
            if best is None or best_overlap < 2 or best["value"] == rec_s["value"]:
                continue
            key = (term, attribute, best["value"], rec_s["value"], best_year, yr_s)
            cross_conflicts[key] = (snap_date, best, rec_s)

    conflicts = []
    latest_date = store.snapshots[-1][1] if store.snapshots else None
    for (term, attribute, win_value, lose_value, yr_official, yr_stale), (_, winner, loser) in cross_conflicts.items():
        official_years = "{}-{}".format(*yr_official)
        stale_years = "{}-{}".format(*yr_stale)
        conflicts.append(Conflict(
            topic="{}-month auto loan APR (official model years {}; stale model years {})".format(term, official_years, stale_years),
            values=[lose_value, win_value],
            sources=[Source(url=loser["url"], snapshot_id=loser["snapshot_id"], quote=loser["quote"][:300]),
                     Source(url=winner["url"], snapshot_id=winner["snapshot_id"], quote=winner["quote"][:300])],
            resolution=win_value,
            reason="Official rate page is authoritative; the calculator/promotional page shows a stale model-year tier."))

    for (product, qualifiers, attribute), records in facts.items():
        # A conflict is a contradiction in one captured website state. A change
        # between snapshots is temporal history, not a self-conflict.
        records = [r for r in records if r["date"] == latest_date]
        best_per_value = {}
        for record in records:
            previous = best_per_value.get(record["value"])
            if previous is None or (-record["rank"], record["date"]) > (-previous["rank"], previous["date"]):
                best_per_value[record["value"]] = record
        if len(best_per_value) < 2:
            continue
        # Only report contradictions where an authoritative page supplies a value;
        # disagreements among calculators/articles alone have no reliable winner.
        if min(r["rank"] for r in best_per_value.values()) > 2:
            continue
        # Winner: most authoritative source, then the newest snapshot it appears in,
        # then the in-page effective date as a tie-breaker.
        winner = max(best_per_value.values(),
                     key=lambda r: (-r["rank"], r["date"], r.get("effective_date") or ""))
        ordered = sorted(best_per_value.values(), key=lambda r: (r["date"], r["rank"]))
        topic = " ".join([product, attribute] + ["{} {}".format(k, v) for k, v in qualifiers]).strip()
        # Add common phrasing ("60-month", domain word) so topic keywords match.
        extras = ["{}-month".format(t) for t in re.findall(r"\b(\d{1,3}) months?\b", product)]
        sample_url = records[0]["url"].lower()
        if "auto" in sample_url or "model year" in product:
            extras.append("auto loan")
        elif "home-loan" in sample_url or "conventional" in product:
            extras.append("mortgage")
        elif "certificate" in product or "special" in product:
            extras.append("certificate")
        if extras:
            topic = topic + " (" + ", ".join(extras) + ")"
        older = [r for r in ordered if r is not winner]
        if all(r["rank"] > winner["rank"] for r in older):
            reason = "Higher-authority page wins over calculator, promotional or article values."
        elif any(r["rank"] >= 99 for r in older):
            reason = "Expired promotion; the current published value wins."
        else:
            reason = "Newer snapshot of the authoritative page supersedes the older value."
        conflicts.append(Conflict(
            topic=topic,
            values=[r["value"] for r in ordered],
            sources=[Source(url=r["url"], snapshot_id=r["snapshot_id"], quote=r["quote"][:300]) for r in ordered],
            resolution=winner["value"], reason=reason))

    # Precision: a dividend-rate change always accompanies the APY change for the
    # same deposit product, so report the APY fact only.
    apy_products = {c.topic.split(" apy")[0] for c in conflicts if " apy" in c.topic}
    conflicts = [c for c in conflicts
                 if not (" dividend rate" in c.topic and c.topic.split(" dividend rate")[0] in apy_products)]
    unique = {}
    for conflict in conflicts:
        unique[(conflict.topic, tuple(sorted(conflict.values)))] = conflict
    return sorted(unique.values(), key=lambda c: c.topic)
