"""Tests for the central routing vocabulary and its handler order."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from knowledge.handlers import HANDLERS  # noqa: E402
from knowledge.routing import EXCLUSIONS, INTENTS, all_of, has, none_of  # noqa: E402


class RoutingVocabularyTests(unittest.TestCase):
    def test_every_pattern_compiles(self):
        import re
        for name, patterns in list(INTENTS.items()) + list(EXCLUSIONS.items()):
            for pattern in patterns:
                with self.subTest(intent=name):
                    re.compile(pattern)

    def test_registry_covers_current_handler_branches(self):
        """Concrete probes keep the shared vocabulary aligned with handler intent branches."""
        probes = {
            "home_start": "what is Home$tart?",
            "membership_subject": "Can I join Dupaco if a family member belongs?",
            "contact_phone_words": "What phone number should I call?",
            "dupaco_reference": "How do I call Dupaco?",
            "locator_link_request": "What is the branch locator URL?",
            "branch_locator_entity": "branch locator URL",
            "student_context": "student loan",
            "student_need": "flexible loan funding",
            "vto": "Volunteer Time Off count",
            "forbes_entity": "Forbes recognition",
            "forbes_action": "Forbes recognized Dupaco",
            "last_year": "How many last year?",
            "checking_subject": "checking rate",
            "mortgage_subject": "mortgage rate",
            "personal_loan_subject": "personal loan APR",
            "certificate_subject": "certificate rate",
            "wallet_card_subject": "add card to a wallet",
            "credit_card_entity": "credit card APR",
            "share_savings_product": "Share Savings balance",
        }
        for intent, phrase in probes.items():
            with self.subTest(intent=intent):
                self.assertTrue(has(intent, phrase))

    def test_membership_link_and_branch_hours_exclusions(self):
        self.assertFalse(none_of("How do I join Dupaco online?", "membership_link"))
        self.assertFalse(none_of("What are the lobby hours?", "branch_hours"))
        self.assertTrue(none_of("Can I join if my sister is a member?", "membership_link"))
    def test_intent_matching_is_case_insensitive(self):
        self.assertTrue(has("home_start", "What is HOME$TART?"))
        self.assertTrue(has("vto", "volunteer TIME off"))

    def test_all_of_requires_every_intent(self):
        self.assertTrue(all_of("who can join dupaco", "membership_subject", "dupaco_reference"))
        self.assertFalse(all_of("what is the weather", "membership_subject", "dupaco_reference"))

    def test_exclusions_block_a_trigger(self):
        self.assertTrue(none_of("how do i join", "membership_link"))
        self.assertFalse(none_of("how do i join online", "membership_link"))
        self.assertFalse(none_of("what are the lobby hours", "branch_hours"))

    def test_wallet_card_pattern_does_not_match_unrelated_card_questions(self):
        # "lost debit card" mentions a card but not a wallet, so it must not reach the wallet handler.
        self.assertFalse(has("wallet_card_subject", "how much is a lost debit card replacement"))
        self.assertTrue(has("wallet_card_subject", "can i add my card to a wallet"))


class RegistryHygieneTests(unittest.TestCase):
    def test_every_registered_intent_is_used_by_a_handler(self):
        """The registry is the single source of truth, so it must not carry dead entries."""
        handlers_dir = Path(__file__).resolve().parent / "knowledge" / "handlers"
        source = "\n".join(p.read_text(encoding="utf8") for p in handlers_dir.glob("*.py"))
        # Exclusion names are used with none_of(); intent names with has()/all_of()/INTENTS[...].
        for name in list(INTENTS) + list(EXCLUSIONS):
            with self.subTest(name=name):
                self.assertIn('"%s"' % name, source, "%s is registered but never used" % name)


class HandlerOrderTests(unittest.TestCase):
    def test_handler_order_is_stable(self):
        """Order matters (first match wins), so a reorder must be a deliberate, reviewed change."""
        self.assertEqual([h.__name__ for h in HANDLERS], [
            "answer_rate_lookup",
            "answer_branch_or_checking",
            "answer_mortgage_rate",
            "answer_product_list",
            "answer_general_fact",
        ])


if __name__ == "__main__":
    unittest.main()
