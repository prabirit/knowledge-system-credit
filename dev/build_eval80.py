#!/usr/bin/env python3
"""Generate dev/eval80.jsonl and dev/conflicts_gold80.json from the RAW snapshot files.

Expected values are parsed straight from snapshots/*/pages/*.md. This file deliberately
does NOT import submission/solution.py, so the answer key cannot echo the system's output.
Run from the repo root:  python3 dev/build_eval80.py
"""
import json
import os
import re
import sys

ROOT = "snapshots"
OUT_EVAL = "dev/eval80.jsonl"
OUT_GOLD = "dev/conflicts_gold80.json"


# ----------------------------------------------------------------- raw parsing
def load():
    snaps = []
    for d in sorted(x for x in os.listdir(ROOT) if x[:2].isdigit()):
        m = json.load(open(f"{ROOT}/{d}/manifest.json"))
        snaps.append({"dir": f"{ROOT}/{d}", "date": m["taken_on"], "manifest": m})
    return snaps


SNAPS = load()


def page_text(snap, suffix):
    for p in snap["manifest"]["pages"]:
        if p["url"].rstrip("/").endswith(suffix):
            return open(f"{snap['dir']}/{p['file']}", encoding="utf8").read()
    return None


def table_rows(text):
    for line in (text or "").splitlines():
        if line.startswith("|") and not re.match(r"^\|\s*-", line):
            yield [c.strip() for c in line.strip("|").split("|")]


def find_row(snap, suffix, pattern):
    text = page_text(snap, suffix)
    for row in table_rows(text):
        if re.search(pattern, " | ".join(row)):
            return row
    return None


def pct(cell):
    """'4.00%1' -> '4.00%' ; '3.90%2' -> '3.90%' ; '5.39% APR1' -> '5.39%'."""
    m = re.search(r"\d+(?:\.\d+)?\s?%", cell or "")
    return m.group(0).replace(" ", "") if m else None


def snap_at(date):
    """Latest snapshot taken on or before `date` (ISO)."""
    eligible = [s for s in SNAPS if s["date"] <= date]
    return eligible[-1] if eligible else None


# --------------------------------------------------------------- question list
ITEMS = []
_counter = [0]


def add(question, expected, must, must_not=None, category="general", as_of=None,
        group=None, sources=None, weight=1.0, refuse=False):
    _counter[0] += 1
    ITEMS.append({
        "id": f"e80-{_counter[0]:03d}",
        "question": question,
        "as_of": as_of,
        "expected_answer": expected,
        "must_include": must,
        "must_not_include": sorted({x for x in (must_not or []) if x} - set(must)),
        "category": "should_refuse" if refuse else category,
        "weight": weight,
        "expected_sources": sources or [],
        "group": group,
    })


def others(values_by_date, keep_date):
    """All values the same fact took at OTHER snapshot dates (stale traps)."""
    return [v for d, v in values_by_date.items() if d != keep_date and v]


# ------------------------------------------------------------------- 1. CDs
CERTS = {
    "10jumbo": (r"^10 Month Fixed Jumbo Certificate Special", "10-month jumbo", "10-month jumbo certificate special"),
    "10std": (r"^10 Month Fixed Certificate Special", "10-month", "10-month fixed certificate special"),
    "17jumbo": (r"^17 Month Fixed Jumbo Certificate Special", "17-month jumbo", "17-month jumbo certificate special"),
    "17std": (r"^17 Month Fixed Certificate Special", "17-month", "17-month fixed certificate special"),
}
cert_hist = {}
for key, (pat, _, _) in CERTS.items():
    cert_hist[key] = {}
    for s in SNAPS:
        row = find_row(s, "dupaco.com/rates", pat)
        cert_hist[key][s["date"]] = pct(row[2]) if row else None   # APY column

# as-of probes: (date, human phrase)
CERT_PROBES = [("2026-05-15", "mid-May 2026"), ("2026-05-25", "late May 2026"),
               ("2026-06-15", "mid-June 2026"), ("2026-07-15", "July 2026"),
               ("2026-09-01", "early September 2026")]
for key in ("10jumbo", "17jumbo", "17std", "10std"):
    pat, short, long = CERTS[key]
    for as_of, phrase in CERT_PROBES:
        snap = snap_at(as_of)
        exp = cert_hist[key][snap["date"]]
        stale = others(cert_hist[key], snap["date"])
        if exp is None:
            continue
        add(f"What was the APY on the {long} in {phrase}?", f"{exp} APY (snapshot {snap['date']})",
            [exp], stale, "temporal_as_of", as_of=as_of, sources=[])
        if key in ("17jumbo", "10jumbo") and as_of in ("2026-06-15", "2026-09-01"):
            break
    # current value, paraphrased group
    exp = cert_hist[key]["2026-09-28"]
    stale = others(cert_hist[key], "2026-09-28")
    g = f"cert-{key}-now"
    add(f"What is the current APY on the {long}?", f"{exp} APY", [exp], stale, "tier_disambiguation", group=g)
    add(f"How much does a {short} special certificate pay in APY right now?", f"{exp} APY", [exp], stale,
        "tier_disambiguation", group=g)
    add(f"Tell me today's APY for the {short} special.", f"{exp} APY", [exp], stale, "tier_disambiguation", group=g)

# products that did not exist yet -> honest "not listed" as of an early date
assert cert_hist["17jumbo"]["2026-05-12"] is None and cert_hist["17jumbo"]["2026-06-09"] is not None
add("What was the APY on the 17-month jumbo certificate special in mid-May 2026?",
    "Not listed on the site as of mid-May 2026 (first appears in the 9 June 2026 snapshot).", [], [],
    as_of="2026-05-15", refuse=True)

# ---------------------------------------------------------------- 2. mortgages
mort = {"30_100k": {}, "15y": {}}
for s in SNAPS:
    r30 = find_row(s, "dupaco.com/rates", r"^Purchase: 30-Year Fixed Conventional \$100,?000 or less")
    r15 = find_row(s, "dupaco.com/rates", r"^Purchase: 15-Year Fixed Conventional")
    mort["30_100k"][s["date"]] = (pct(r30[1]), pct(r30[3]))     # (rate, APR)
    mort["15y"][s["date"]] = (pct(r15[1]), pct(r15[3]))

MORT_PROBES = [("2026-05-15", "mid-May 2026"), ("2026-05-25", "late May 2026"),
               ("2026-06-15", "mid-June 2026"), ("2026-09-01", "early September 2026")]
for as_of, phrase in MORT_PROBES:
    snap = snap_at(as_of)
    rate, apr = mort["30_100k"][snap["date"]]
    stale = [v[0] for d, v in mort["30_100k"].items() if d != snap["date"]]
    add(f"What was the 30-year fixed purchase mortgage rate for a loan of $100,000 or less in {phrase}?",
        f"{rate} rate / {apr} APR", [rate, apr], stale, "temporal_as_of", as_of=as_of)
for as_of, phrase in MORT_PROBES[1:3]:
    snap = snap_at(as_of)
    rate, apr = mort["15y"][snap["date"]]
    stale = [v[0] for d, v in mort["15y"].items() if d != snap["date"]]
    add(f"What was the 15-year fixed purchase mortgage rate in {phrase}?", f"{rate} rate / {apr} APR",
        [rate], stale, "temporal_as_of", as_of=as_of)

rate, apr = mort["30_100k"]["2026-09-28"]
stale30 = [v[0] for d, v in mort["30_100k"].items() if d != "2026-09-28"]
g = "mort-30-100k"
add("What is the 30-year fixed purchase rate for a loan up to $100,000?", f"{rate} / {apr} APR", [rate, apr],
    stale30 + ["7.25%"], "tier_disambiguation", group=g)
add("I'm borrowing $100,000 on a 30-year mortgage to buy a home - what rate would I get?", f"{rate} / {apr} APR",
    [rate], stale30 + ["7.25%"], "tier_disambiguation", group=g)
add("Current purchase mortgage rate, 30 years, $100k or less?", f"{rate} / {apr} APR", [rate],
    stale30 + ["7.25%"], "tier_disambiguation", group=g)

r200 = find_row(SNAPS[-1], "dupaco.com/rates", r"^Purchase: 30-Year Fixed Conventional \$200,000 or less")
r832 = find_row(SNAPS[-1], "dupaco.com/rates", r"^Purchase: 30-Year Fixed Conventional \$832,750 or less")
add("What rate would I get on a $180,000 30-year purchase mortgage?", f"{pct(r200[1])} / {pct(r200[3])} APR",
    [pct(r200[1]), pct(r200[3])], ["7.13%"] + stale30, "tier_disambiguation")
add("What is the 30-year purchase mortgage rate for a loan up to $832,750?", f"{pct(r832[1])} / {pct(r832[3])} APR",
    [pct(r832[1]), pct(r832[3])], ["7.13%"] + stale30, "tier_disambiguation")
r15 = mort["15y"]["2026-09-28"]
add("What's today's 15-year fixed mortgage rate?", f"{r15[0]} / {r15[1]} APR", [r15[0], r15[1]],
    [v[0] for d, v in mort["15y"].items() if d != "2026-09-28"], "current_value", group="mort-15")
add("How much interest on a 15 year home loan right now?", f"{r15[0]} / {r15[1]} APR", [r15[0], r15[1]],
    [v[0] for d, v in mort["15y"].items() if d != "2026-09-28"], "current_value", group="mort-15")

# ------------------------------------------------------------- 3. auto loans
auto = {}
AUTO_CASES = [  # (year, months, label)
    (2025, 60), (2024, 84), (2022, 60), (2019, 72), (2016, 48), (2023, 72)]
for s in SNAPS:
    text = page_text(s, "personal/loans/auto-motorcycle-loans")
    for row in table_rows(text):
        j = " | ".join(row)
        m = re.match(r"^(\d{4})\s*[-\u2013]\s*(\d{2,4})\s+Model Year \| (\d+) Months \| (\d+\.\d+)% APR", j)
        if m:
            a, b, months = int(m.group(1)), int(m.group(2)), int(m.group(3))
            b = (a // 100) * 100 + b if b < 100 else b
            auto.setdefault(s["date"], []).append((a, b, months, m.group(4) + "%"))
        m2 = re.match(r"^2016 Model Year \(and older\) \| (\d+) Months \| (\d+\.\d+)% APR", j)
        if m2:
            auto.setdefault(s["date"], []).append((0, 2016, int(m2.group(1)), m2.group(2) + "%"))


def auto_rate(date, year, months):
    for a, b, mo, v in auto[date]:
        if mo == months and a <= year <= b:
            return v
    return None


# stale calculator values on the CURRENT site (switch-and-earn / calculator pages) - parsed raw
calc_vals = set()
for suffix in ("switch-and-earn", "calculators/vehicle-affordability"):
    for row in table_rows(page_text(SNAPS[-1], suffix)):
        j = " | ".join(row)
        m = re.match(r"^\d{4}[-\u2013]\d{2} Model Year \| \d+\s+Months \| (\d+\.\d+)% APR", j)
        if m:
            calc_vals.add(m.group(1) + "%")

for year, months in AUTO_CASES:
    now = auto_rate("2026-09-28", year, months)
    past = auto_rate("2026-06-09", year, months)
    hist = {d: auto_rate(d, year, months) for d in auto}
    stale_now = [v for d, v in hist.items() if d != "2026-09-28"] + [c for c in calc_vals if c != now]
    g = f"auto-{year}-{months}"
    add(f"What's the APR for a {months}-month auto loan on a {year} model-year vehicle?", f"{now} APR", [now],
        stale_now, "stale_trap", group=g)
    add(f"How much would financing a {year} car over {months} months cost in APR?", f"{now} APR", [now],
        stale_now, "stale_trap", group=g)
    add(f"Auto loan APR, {year} vehicle, {months} months?", f"{now} APR", [now], stale_now, "stale_trap", group=g)
    if past and past != now:
        stale_past = [v for d, v in hist.items() if d != "2026-06-09"] + list(calc_vals)
        add(f"What was the {months}-month auto loan APR for a {year} model year as of June 2026?", f"{past} APR",
            [past], [x for x in stale_past if x != past], "temporal_as_of", as_of="2026-06-15")
        if year == 2025:
            break_after = True

# ----------------------------------------------------------- 4. personal loans
for months in (24, 36, 48, 60):
    row = find_row(SNAPS[-1], "personal/loans/personal-loans", rf"^{months} Months")
    val = pct(row[1])
    other = [pct(find_row(SNAPS[-1], "personal/loans/personal-loans", rf"^{m} Months")[1])
             for m in (24, 36, 48, 60) if m != months]
    other = [o for o in other if o != val]
    g = f"pl-{months}"
    add(f"What is the APR on a {months}-month personal loan?", f"{val} APR", [val], other, "tier_disambiguation", group=g)
    add(f"If I take a personal loan for {months} months, what APR applies?", f"{val} APR", [val], other,
        "tier_disambiguation", group=g)

# ------------------------------------------------------- 5. savings / deposits
rates_latest = SNAPS[-1]


def deposit(account, tier_pat):
    return find_row(rates_latest, "dupaco.com/rates", rf"^{account} \| {tier_pat}")


for label, tier_pat, phrase in [("0.15%", r"\$10,000", "between $10,000 and $24,999.99"),
                                ("0.20%", r"\$25,000\+", "of $25,000 or more"),
                                ("0.10%", r"\$2,500", "between $2,500 and $9,999.99")]:
    g = f"share-{label}"
    add(f"What APY does Share Savings pay on a balance {phrase}?", f"{label} APY", [label],
        ["0.35%", "0.30%", "0.40%"], "tier_disambiguation", group=g)
    add(f"Share Savings: what do I earn if my balance is {phrase.replace('between', 'in the range of')}?",
        f"{label} APY", [label], ["0.35%", "0.30%", "0.40%"], "tier_disambiguation", group=g)

MM_TIERS = {"top": r"\$100,000\+", "mid": r"\$25,000", "low": r"\$10,000", "small": r"\$2,500"}
mm_raw = {k: pct(deposit("Investor's Choice Money Market", pat)[3]) for k, pat in MM_TIERS.items()}
add("What APY does the Investor's Choice Money Market pay on $100,000 or more?", mm_raw["top"] + " APY",
    [mm_raw["top"]], [mm_raw["mid"], mm_raw["low"], mm_raw["small"]], "tier_disambiguation")
add("Investor's Choice Money Market APY for a balance between $25,000 and $99,999.99?", mm_raw["mid"] + " APY",
    [mm_raw["mid"]], [mm_raw["top"], mm_raw["low"], mm_raw["small"]], "tier_disambiguation")

hy = pct(deposit("High-Yield Savings", r"\$1,000,000\+")[3])
add("What's the APY on High-Yield Savings for a balance of $1,000,000 or more?", f"{hy} APY", [hy],
    [], "tier_disambiguation")
bright = deposit("Bright Savings", r"\$0\.01")
add("What is the APY on Bright Savings?", f"{pct(bright[3])} APY ({pct(bright[2])} dividend rate)", [pct(bright[3])],
    ["0.35%"], "entity_attribution", group="bright")
add("How much interest does an online Bright Savings account earn?", f"{pct(bright[3])} APY", [pct(bright[3])],
    ["0.35%"], "entity_attribution", group="bright")
add("What is Bright Savings' dividend rate (not the APY)?", f"{pct(bright[2])} dividend rate", [pct(bright[2])],
    [], "entity_attribution")
lp = deposit("Launchpad Savings", r"\$5")
add("What is the APY on Launchpad Savings?", f"{pct(lp[3])} APY", [pct(lp[3])], [], "entity_attribution")
_t = page_text(SNAPS[2], "personal/retirement") or ""
assert "| Launchpad Savings | 3.21% | 3.25% |" in _t, "Launchpad row missing from June snapshot"
add("What APY did Launchpad Savings pay in June 2026?",
    "3.25% APY (listed on the retirement page in the 2026-06-09 snapshot)", ["3.25%"], [],
    "temporal_as_of", as_of="2026-06-15")
chk = deposit("1st Rate Checking", r"\$5,000")
add("What APY does 1st Rate Checking pay on a balance of $5,000 to $24,999.99?", f"{pct(chk[3])} APY", [pct(chk[3])],
    ["3% APY"], "tier_disambiguation")

# ------------------------------------------------------- 6. credit cards
card_text = page_text(SNAPS[-1], "personal/credit-cards")
assert "12.50%" in card_text and "19.50%" in card_text and "15.50%" in card_text and "21.00%" in card_text
add("What is the standard APR range on the Platinum Visa?", "12.50%-19.50% APR", ["12.50%", "19.50%"],
    ["21.00%"], "tier_disambiguation", group="platinum")
add("How much APR would I pay on a Dupaco Platinum Visa card if I carry a balance?", "12.50%-19.50% APR",
    ["12.50%", "19.50%"], ["21.00%"], "tier_disambiguation", group="platinum")
add("What APR does the Rewards Visa charge?", "15.50%-21.00% APR", ["15.50%", "21.00%"], ["12.50%"],
    "tier_disambiguation", group="rewards")
add("Rewards Visa interest rate?", "15.50%-21.00% APR", ["15.50%", "21.00%"], ["12.50%"],
    "tier_disambiguation", group="rewards")
add("What is the introductory balance transfer APR on the Platinum Visa?", "2.90% intro APR for 6 months",
    ["2.90%"], [], "entity_attribution")
add("What is the APR on the Business Rewards Visa?", "20.50% variable APR", ["20.50%"], ["15.50%"],
    "entity_attribution")
add("What is the Business Platinum Visa APR?", "15.50% variable APR", ["15.50%"], ["20.50%"], "entity_attribution")

# --------------------------------------------- 7. contact, branches, locations
contact = page_text(SNAPS[-1], "/contact")
assert "273974581" in contact and "800-373-7600" in contact and "11375 Oldenburg Ln., Galena, IL, 61036" in contact
add("What routing number should I use for direct deposit?", "273974581", ["273974581"], [], "entity_attribution",
    group="routing")
add("Dupaco ABA routing number?", "273974581", ["273974581"], [], "entity_attribution", group="routing")
add("What is the phone number to call Dupaco?", "800-373-7600", ["800-373-7600"], [], "current_value", group="phone")
add("How do I reach Dupaco by phone?", "800-373-7600", ["800-373-7600"], [], "current_value", group="phone")
add("What is the street address of the Galena, Illinois branch?", "11375 Oldenburg Ln., Galena, IL 61036",
    ["11375 Oldenburg", "61036"], ["unable to find"], "branch_info", group="galena")
add("Where is the Galena branch located?", "11375 Oldenburg Ln., Galena, IL 61036", ["11375 Oldenburg", "61036"],
    ["unable to find"], "branch_info", group="galena")
add("Is there a Dupaco branch address for Peosta?", "185 Peosta St., Peosta, IA 52068", ["185 Peosta", "52068"], [],
    "branch_info")
add("What is the address of the Flint Hill branch?", "2245 Flint Hill Dr., Dubuque, IA 52003",
    ["2245 Flint Hill", "52003"], [], "branch_info")
add("When does the Hy-Vee branch close?", "March 31, 2026", ["March 31, 2026"], [], "temporal_as_of", group="hyvee")
add("Is the Hy-Vee branch still operating today?", "No - it was scheduled to close March 31, 2026",
    ["March 31, 2026"], [], "temporal_as_of", group="hyvee")
add("Which branches can Hy-Vee branch members use after it closes?", "Key West and Sycamore Street",
    ["Key West", "Sycamore"], ["CO-OP Shared Branch"], "branch_info")
add("What is the URL to find a Dupaco branch or ATM?", "https://www.dupaco.com/contact", ["dupaco.com/contact"],
    ["/locations/branch-hours"], "stale_trap", group="locator")
add("Where can I find a branch or ATM locator?", "https://www.dupaco.com/contact", ["dupaco.com/contact"],
    ["/locations/branch-hours"], "stale_trap", group="locator")

# --------------------------------------------------------- 8. prose / program facts
join = page_text(SNAPS[-1], "about/join")
assert "join.dupaco.com" in join and "charter area" in join
add("How much assistance does Home$tart give first-time homebuyers?", "Up to $15,000 toward down payment and closing costs",
    ["$15,000"], [], "current_value", group="homestart")
add("What is the FHLB Home$tart grant amount?", "Up to $15,000", ["$15,000"], [], "current_value", group="homestart")
add("How many employees used Volunteer Time Off in 2023?", "294 employees", ["294"], [], "temporal_as_of", group="vto")
add("In 2023, how many Dupaco staff took Volunteer Time Off?", "294 employees", ["294"], [], "temporal_as_of", group="vto")
add("How many times has Forbes recognized Dupaco as a Best-in-State credit union?", "Five times (the fifth time in 2024)",
    ["fifth"], ["fourth"], "stale_trap")
add("Who can become a Dupaco member?", "People who live or work in the charter area (Iowa, Illinois, Wisconsin)",
    ["Iowa", "Illinois", "Wisconsin"], [], "conflict_resolution", group="eligible")
add("Am I eligible to join Dupaco if I live in Wisconsin?", "Yes, living or working in the charter area qualifies",
    ["Wisconsin"], [], "conflict_resolution", group="eligible")
add("What is the online link to become a Dupaco member?", "https://join.dupaco.com/", ["join.dupaco.com"],
    ["info.dupaco.com/how_to_join"], "stale_trap")
add("Which mobile wallets work with Dupaco cards?", "Apple Pay, Google Pay and Samsung Pay",
    ["Apple Pay", "Google Pay", "Samsung Pay"], [], "list_completeness", group="wallet")
add("Can I use Apple Pay with my Dupaco debit card?", "Yes - Apple Pay, Google Pay and Samsung Pay are supported",
    ["Apple Pay"], [], "list_completeness", group="wallet")
add("Do you offer student loans, and are the repayment terms flexible?",
    "Student loans (new or refinance) with flexible repayment and $0 origination fees", ["student loan", "flexible"],
    ["Share Savings"], "entity_attribution", group="student")
add("I need money for college - what loan options do you have?", "Student loans with flexible repayment",
    ["student loan"], ["Share Savings"], "entity_attribution", group="student")
add("What link shows Dupaco's certificate rates?", "https://www.dupaco.com/personal/savings-account#rates",
    ["dupaco.com/personal/savings-account"], ["info.dupaco.com/certificate_account_rates"], "stale_trap")

# --------------------------------------------------------------- 9. refusals
refusals = [
    ("What is the rate on a 7/1 ARM?", "Not published"),
    ("Do you publish a rate for adjustable-rate mortgages like a 5/1 ARM?", "Not published"),
    ("What interest rate do you charge on a land construction loan?", "Not published"),
    ("What are the lobby hours at the Mullan Avenue branch?", "No grounded hours for that branch"),
    ("What is the APY on a 120-month certificate?", "No 120-month certificate is listed"),
    ("What is the APR on a 7-year student loan?", "Not published on the Dupaco site"),
]
for q, why in refusals:
    add(q, why, [], [], refuse=True)
add("What was the 6-month certificate APY in April 2026?",
    "No website snapshot exists from before 12 May 2026", [], [], as_of="2026-04-15", refuse=True)

# ----------------------------------------------------------------------- output
os.makedirs("dev", exist_ok=True)
with open(OUT_EVAL, "w") as fh:
    for it in ITEMS:
        fh.write(json.dumps(it) + "\n")

# ------------------------------------------------------------ conflicts gold
# Contradictions on the CURRENT website (snapshot 05): a calculator/promo page or old guide page
# shows a different value than the official page. Every value is verified in the raw text below.
GOLD = []


def verify(page_suffix, needle):
    t = page_text(SNAPS[-1], page_suffix)
    assert t and needle in t, (page_suffix, needle)


for months, (stale, official) in {60: ("5.34%", "5.39%"), 72: ("5.44%", "5.49%"), 84: ("5.54%", "5.59%")}.items():
    verify("switch-and-earn", f"| {months} Months | {stale} APR")
    verify("personal/loans/auto-motorcycle-loans", f"| {months} Months | {official} APR")
    GOLD.append({"id": f"g-auto-new-{months}", "topic_keywords": [f"{months}-month"],
                 "values": [stale, official], "correct_value": official})
for months, (stale, official) in {60: ("5.59%", "5.64%"), 72: ("5.74%", "5.79%"), 84: ("5.99%", "6.04%")}.items():
    verify("switch-and-earn", f"| {months} Months | {stale} APR")
    verify("personal/loans/auto-motorcycle-loans", f"| {months} Months | {official} APR")
    GOLD.append({"id": f"g-auto-mid-{months}", "topic_keywords": [f"{months}-month"],
                 "values": [stale, official], "correct_value": official})
for months, (stale, official) in {60: ("6.29%", "6.34%"), 72: ("6.44%", "6.49%")}.items():
    verify("switch-and-earn", f"| {months} Months | {stale} APR")
    verify("personal/loans/auto-motorcycle-loans", f"| {months} Months | {official} APR")
    GOLD.append({"id": f"g-auto-old-{months}", "topic_keywords": [f"{months}-month"],
                 "values": [stale, official], "correct_value": official})

for tier, label in [("$100,000 or less", "100,000"), ("$200,000 or less", "200,000"),
                    ("$300,000 or less", "300,000"), ("$832,750 or less", "832,750")]:
    off = find_row(SNAPS[-1], "dupaco.com/rates", rf"^Purchase: 30-Year Fixed Conventional {re.escape(tier)}")
    stale_row = find_row(SNAPS[-1], "homebuying-guidance",
                         rf"^Purchase: 30-Year Fixed Conventional \$?{label.replace(',', ',?')} or less")
    assert off and stale_row, tier
    GOLD.append({"id": f"g-mort-{label}", "topic_keywords": ["30-year", label.replace(",", "")],
                 "values": [pct(stale_row[1]), pct(off[1])], "correct_value": pct(off[1])})
off15 = find_row(SNAPS[-1], "dupaco.com/rates", r"^Purchase: 15-Year Fixed Conventional")
st15 = find_row(SNAPS[-1], "homebuying-guidance", r"^Purchase: 15-Year Fixed Conventional")
GOLD.append({"id": "g-mort-15", "topic_keywords": ["15-year"],
             "values": [pct(st15[1]), pct(off15[1])], "correct_value": pct(off15[1])})

json.dump(GOLD, open(OUT_GOLD, "w"), indent=1)

from collections import Counter
print("questions:", len(ITEMS), "| groups:", len({i['group'] for i in ITEMS if i['group']}),
      "| conflicts gold:", len(GOLD))
print(Counter(i["category"] for i in ITEMS))
