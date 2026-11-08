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


if __name__ == "__main__":
    unittest.main()
