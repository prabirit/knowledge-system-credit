"""Small regression tests for evidence-based conflict handling."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_eval import load_snapshots  # noqa: E402
from solution import build  # noqa: E402


class ConflictRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.system = build()
        cls.snapshots = load_snapshots(ROOT / "harness" / "selftest" / "snapshots")
        for snapshot in cls.snapshots:
            cls.system.ingest(snapshot)

    def test_snapshot_history_is_not_reported_as_self_conflict(self):
        """A normal old/new value is history; report it only where page evidence conflicts."""
        conflicts = self.system.conflicts()
        self.assertEqual(len(conflicts), 1)
        conflict = conflicts[0]
        self.assertIn("6-month certificate", conflict.topic)
        self.assertEqual(set(conflict.values), {"2.95%", "3.50%"})
        self.assertEqual(conflict.resolution, "3.50%")
        self.assertTrue(conflict.sources)

    def test_as_of_uses_the_appropriate_snapshot(self):
        historical = self.system.answer("What was the 6-month certificate APY in January 2026?", as_of="2026-01-31")
        latest = self.system.answer("What is the 6-month certificate APY?")
        self.assertIn("2.95%", historical.text)
        self.assertNotIn("3.50%", historical.text)
        self.assertIn("3.50%", latest.text)
        self.assertNotIn("2.95%", latest.text)

    def test_missing_certificate_term_declines(self):
        answer = self.system.answer("What is the 60-month jumbo certificate rate?")
        self.assertFalse(answer.confident)

    def test_certificate_list_question_returns_all_current_terms(self):
        """The public scorer has no must-include tokens for this item, so test completeness directly."""
        system = build()
        latest = load_snapshots(ROOT / "snapshots")[-1]
        system.ingest(latest)
        answer = system.answer("Get me the rate for the certificate of accounts.")
        for term in ("17 Month Fixed Jumbo", "17 Month Fixed Certificate",
                     "10 Month Fixed Jumbo", "10 Month Fixed Certificate",
                     "60 Month", "48 Month", "36 Month", "30 Month", "24 Month",
                     "18 Month", "12 Month", "6 Month"):
            with self.subTest(term=term):
                self.assertIn(term, answer.text)
        self.assertNotIn("Which certificate term would you like", answer.text)
        self.assertEqual(len(answer.sources), 1)
        self.assertTrue(answer.sources[0].url.endswith("/rates"))


class DerivedAnswerTests(unittest.TestCase):
    """Reworded questions must be answered from page evidence, not fixed answer text."""

    @classmethod
    def setUpClass(cls):
        cls.system = build()
        for snapshot in load_snapshots(ROOT / "snapshots"):
            cls.system.ingest(snapshot)

    def ask(self, question):
        return self.system.answer(question)

    def test_vto_count_follows_the_requested_year(self):
        self.assertIn("256", self.ask("How many Dupaco employees used Volunteer Time Off in 2024?").text)
        self.assertIn("294", self.ask("How many Dupaco employees used Volunteer Time Off in 2023?").text)
        missing = self.ask("How many Dupaco employees used Volunteer Time Off in 2019?")
        self.assertFalse(missing.confident)

    def test_rate_membership_question_checks_every_tier(self):
        yes = self.ask("Do any Share Savings tiers pay 0.10% APY?").text
        self.assertTrue(yes.startswith("Yes"))
        no_share = self.ask("Do any Dupaco savings tiers pay 0.35% APY?").text
        self.assertIn("0.20%", no_share)
        self.assertIn("Health Savings Account", no_share)

    def test_forbes_article_matches_the_question(self):
        employer = self.ask("Has Forbes ranked Dupaco as a top small employer?").text
        self.assertIn("employer", employer.lower())
        credit_union = self.ask("What recognition has Dupaco received from Forbes?").text
        self.assertIn("fifth", credit_union)

    def test_eligibility_includes_family_rule(self):
        text = self.ask("Can I join Dupaco if my brother is a member?").text
        self.assertIn("immediate family member", text)


if __name__ == "__main__":
    unittest.main()
