#!/usr/bin/env python3
"""Record (or compare) the exact outputs of a submission, for behavior-preserving refactors.

    python3 dev/golden_snapshot.py record  /tmp/golden_before.json
    python3 dev/golden_snapshot.py compare /tmp/golden_before.json

It asks every question from the public / hold-out / eval80 / self-test sets plus extra edge-case
probes, at the question's own `as_of`, and also at several fixed dates. It stores the full answer
(text, confidence, sources) and the full `conflicts()` output. `compare` reports any difference.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "submission"))

from run_eval import load_snapshots  # noqa: E402
from solution import build  # noqa: E402

EXTRA = [
    "What is the 12-month certificate APY?", "6 month CD rate", "What is the 25-month certificate rate?",
    "How much is the 17-month jumbo special?", "Which certificate terms do you offer?",
    "What are the mortgage rates for a $250,000 loan?", "20-year mortgage rate?", "What is the refinance rate?",
    "auto loan rate for 2023 vehicle 48 months", "motorcycle loan APR 36 months", "boat loan rate",
    "personal loan 72 months", "HELOC rate", "home equity loan APR",
    "How do I contact Dupaco?", "What's the email for the mortgage team?", "Where is the Sycamore Street branch?",
    "address of the Hillcrest branch", "Is there an ATM in Cuba City?", "Platteville branch hours",
    "When did the Asbury branch close?", "Which branch is in Peosta?", "Is the Hy-Vee branch open?",
    "How many branches does Dupaco have?", "How many members does Dupaco have?", "When was Dupaco founded?",
    "What is the Bright Savings APY?", "HSA interest rate", "Holiday Club rate", "High-Yield Savings $500,000",
    "money market $30,000", "checking account rate", "Free Checking APY", "business checking rate",
    "What credit cards do you offer?", "Platinum Visa APR", "Business Rewards APR", "balance transfer APR",
    "Do you offer student loans?", "student loan refinance limit", "How do I join?", "Who can join Dupaco?",
    "Which mobile wallets are supported?", "Do you charge for Apple Pay?", "What is Home$tart?",
    "How many employees volunteered?", "Forbes recognition", "Has Dupaco been named a top workplace?",
    "Do any savings accounts pay 2.25%?", "Does any tier pay 3.25% APY?", "What is the highest APY?",
    "What is the CD rate link?", "branch locator url", "routing number", "What is the swift code?",
    "Do you offer cryptocurrency accounts?", "What is the 7/1 ARM rate?", "construction loan APR",
    "What is the weather today?", "", "asdf qwerty", "a",
]
AS_OF_PROBES = ["2026-04-01", "2026-05-12", "2026-05-15", "2026-06-09", "2026-07-20", "2026-08-27", "2026-12-31"]
AS_OF_QUESTIONS = ["What is the 10-month jumbo certificate APY?", "What is the 30-year mortgage rate for $100,000?",
                   "What is the auto loan APR for a 2025 vehicle for 60 months?", "How many branches does Dupaco have?",
                   "What is the Bright Savings APY?", "Is the Hy-Vee branch still open?"]


def questions():
    out = []
    for path in ["eval/public_eval.jsonl", "dev/holdout_eval.jsonl", "dev/eval80.jsonl", "harness/selftest/eval.jsonl"]:
        for line in (ROOT / path).read_text().splitlines():
            if line.strip():
                item = json.loads(line)
                out.append((path, item["question"], item.get("as_of")))
    out += [("extra", q, None) for q in EXTRA]
    out += [("asof", q, d) for q in AS_OF_QUESTIONS for d in AS_OF_PROBES]
    return out


def run(system_snapshots):
    ks = build()
    for snap in system_snapshots:
        ks.ingest(snap)
    answers = []
    for src, q, as_of in questions():
        a = ks.answer(q, as_of=as_of)
        answers.append({"src": src, "q": q, "as_of": as_of, "text": a.text, "confident": a.confident,
                        "note": a.conflict_note,
                        "sources": [[s.url, s.snapshot_id, s.quote] for s in (a.sources or [])]})
    conflicts = [{"topic": c.topic, "values": c.values, "resolution": c.resolution, "reason": c.reason,
                  "sources": [[s.url, s.snapshot_id, s.quote] for s in c.sources]} for c in ks.conflicts()]
    return answers, conflicts


def main():
    mode, path = sys.argv[1], Path(sys.argv[2])
    main_snaps = load_snapshots(ROOT / "snapshots")
    self_snaps = load_snapshots(ROOT / "harness" / "selftest" / "snapshots")
    t = time.time()
    answers, conflicts = run(main_snaps)
    # self-test fixture answered against its own snapshots
    st_ans, st_conf = run(self_snaps)
    result = {"answers": answers, "conflicts": conflicts, "selftest_answers": st_ans, "selftest_conflicts": st_conf}
    blob = json.dumps(result, sort_keys=True, ensure_ascii=False)
    if mode == "record":
        path.write_text(blob)
        print(f"recorded {len(answers)} answers, {len(conflicts)} conflicts, "
              f"{len(st_ans)} selftest answers  sha256={hashlib.sha256(blob.encode()).hexdigest()[:16]}  ({time.time()-t:.1f}s)")
        return 0
    before = json.loads(path.read_text())
    diffs = 0
    for key in ("answers", "selftest_answers"):
        for old, new in zip(before[key], result[key]):
            if old != new:
                diffs += 1
                if diffs <= 15:
                    print(f"DIFF [{key}] {old['src']} | {old['q'][:70]!r} as_of={old['as_of']}")
                    for field in ("text", "confident", "sources"):
                        if old[field] != new[field]:
                            print(f"   {field}: {str(old[field])[:160]!r}\n      -> {str(new[field])[:160]!r}")
        if len(before[key]) != len(result[key]):
            print(f"LENGTH differs for {key}: {len(before[key])} vs {len(result[key])}")
            diffs += 1
    for key in ("conflicts", "selftest_conflicts"):
        if before[key] != result[key]:
            diffs += 1
            print(f"DIFF in {key}: {len(before[key])} before vs {len(result[key])} now")
    print("IDENTICAL" if diffs == 0 else f"{diffs} difference(s)")
    return 0 if diffs == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
