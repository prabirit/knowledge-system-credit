"""Regression tests for the knowledge-system submission."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_eval import load_snapshots  # noqa: E402
from solution import build  # noqa: E402


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
