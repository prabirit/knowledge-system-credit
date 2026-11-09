"""Central question-routing vocabulary.

Handler triggers live here rather than being scattered across answer handlers. The patterns are
kept intentionally small and explicit; handler modules still own the corresponding evidence lookup
and answer formatting. Review changes against the golden snapshot before altering these patterns.
"""
from __future__ import annotations

import re

INTENTS = {
    # General facts / membership / service
    "home_start": (r"hometart", r"home\$tart"),
    "membership_subject": (r"\b(eligib\w*|who can join|can i join|become (?:a |an )?(?:dupaco )?member|join dupaco)\b",),
    "membership_question": (r"\b(eligible|join|membership|who)\b",),
    "contact_phone_words": (r"\b(phone|telephone|call)\b",),
    "dupaco_reference": (r"\b(dupaco|you|your|us)\b",),
    "phone_specific_exclusion": (r"\b(lost|stolen|card|loan|mortgage|hsa|insurance|business|update|change|edit|ext|extension)\b",),
    "locator_link_request": (r"\b(url|link|locator|website|web page|webpage)\b",),
    "branch_locator_entity": (r"\b(branch|atm|locator|location)\b",),
    "named_branch_event": (r"([A-Z][\w-]+(?:\s[A-Z][\w-]+)*)\s+(?:branch|location)\b",),
    "closure_event": (r"\b(close|closes|closed|closing|closure|still|operating|open|members|go|after|instead)\b",),
    "branch_event_alternatives": (r"\b(members|go|where|instead|full-service)\b",),
    "event_branch_hours": (r"\b(hours?|lobby|drive[- ]?up)\b",),
    "contact_update_action": (r"\b(update|change|edit)\b",),
    "contact_fields": (r"\b(contact information|phone number|email address|address)\b",),
    "student_context": (r"\b(student|college|university|school|tuition)\b",),
    "student_need": (r"\b(loan|funding|repayment|flexible)\b",),
    "student_rate_question": (r"\b(apr|rate|rates|interest)\b",),
    "student_flexible_text": (r"flexible terms",),
    "student_no_fee_text": (r"\$0 origination fees",),
    "vto": (r"volunteer time off", r"\bvto\b"),
    "forbes_entity": (r"forbes",),
    "forbes_action": (r"\b(recogni[sz]ed|recognition|award|rank|ranked|named|top)\b",),
    "forbes_employer_subject": (r"\b(employer|workplace|work)\b",),
    "join_action": (r"\b(join|become (?:a |an )?(?:dupaco )?(?:new )?member)\b",),
    "online_link_context": (r"\b(online|website|link|url)\b",),
    "last_year": (r"last year",),
    "specialized_rate_ask": (r"\b7\s*/\s*1\b|\b7\s*[- ]?year arm\b|\badjustable[- ]rate (?:mortgage|loan)\b|\barm\b",),
    "construction_subject": (r"construction",),
    "rate_question": (r"\b(rate|rates|apr|apy|interest)\b",),
    "rate_present": (r"\d+(?:\.\d+)?\s*%",),
    "branch_location_subject": (r"\b(branch|location)\b",),
    "location_hours_open": (r"\b(hours?|open|close|closing|lobby|drive[- ]?up)\b",),
    "named_location_phrase": (r"\b(?:for|at|of)\s+(?:the\s+)?(.+?)\s+(?:branch|location)\b",),
    "location_time": (r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b",),

    # Rates / product types
    "rate_words": (r"\b(rate|rates|apy|apr|interest|dividend|earn|pay|pays|yield)\b",),
    "checking_subject": (r"checking",),
    "checking_rate_words": (r"\b(rate|rates|apy|interest|dividend)\b",),
    "address_words": (r"\b(address|where|located|location|street)\b",),
    "branch_address_entity": (r"\b(branch|office|atm|located|address)\b",),
    "hours_words": (r"\b(lobby|drive[- ]?up)\s+hours\b|\bhours\s+(?:for|of)\s+(?:the\s+)?(?:lobby|drive[- ]?up)\b",),
    "drive_up": (r"drive[- ]?up",),
    "mortgage_subject": (r"\b(mortgage|home loan)\b",),
    "mortgage_rate_words": (r"\b(rate|rates|interest|apr)\b",),
    "thirty_year": (r"30-year", r"30 year"),
    "loan_amount": (r"\$",),
    "personal_loan_subject": (r"personal loan",),
    "named_rate_words": (r"\b(rate|rates|apy|apr|interest|dividend|earn|pay|pays|yield)\b",),
    "any_tier_query": (r"\b(any|which|is there|does|do)\b",),
    "tier_entity": (r"\b(tier|tiers|account|accounts|savings|pay|pays)\b",),
    "rate_amount": (r"(\d+(?:\.\d+)?)\s?%",),
    "certificate_subject": (r"certificate", r"\bcd\b"),
    "certificate_special_term": (r"\bspecial\b",),
    "month_term": (r"\b\d+\s*[- ]?\s*months?\b",),
    "certificate_rate_words": (r"\b(rate|rates|apy|apr|certificate of accounts)\b",),
    "certificate_link_words": (r"\b(link|url|where can i|what link)\b",),
    "wallet_subject": (r"mobile wallet",),
    "wallet_card_subject": (r"wallet.*card|card.*wallet",),
    "auto_vehicle_subject": (r"\b(auto|vehicle|car)\b",),
    "business_context": (r"business",),
    "dividend_attribute": (r"dividend",),
    "jumbo_qualifier": (r"jumbo",),
    "share_savings_product": (r"share savings",),
    "savings_domain": (r"savings",),
    "atm_entity": (r"atm",),
    "credit_card_entity": (r"credit card",),
    "credit_card_rate_words": (r"\b(rate|rates|apr|offer|offers|what|which|interest)\b",),
    "platinum_visa_entity": (r"\bplatinum\s+visa\b",),
    "rewards_visa_entity": (r"\brewards\s+visa\b",),
    "visa_rate_entity": (r"\bvisa\b.*\b(apr|interest|rate)\b",),
}

EXCLUSIONS = {
    "membership_link": (r"\b(online|website|link|url|apply)\b",),
    "branch_hours": (r"\b(hours?|lobby|drive[- ]?up)\b",),
    "locator_link": (r"\b(hours?|open|close|closing|address|members?)\b",),
    "credit_card_list": (r"intro|balance transfer|lost|stolen|point|redeem|cash advance|fee|terms|wallet|apple|google|samsung|debit|pay\b",),
}


def has(intent: str, text: str) -> bool:
    """Return true if any registered pattern for an intent matches text."""
    lowered = (text or "").lower()
    return any(re.search(pattern, lowered) for pattern in INTENTS[intent])


def all_of(text: str, *intents: str) -> bool:
    """Return true if every named intent pattern matches text."""
    return all(has(intent, text) for intent in intents)


def none_of(text: str, exclusion: str) -> bool:
    """Return true if no registered exclusion pattern matches text."""
    lowered = (text or "").lower()
    return not any(re.search(pattern, lowered) for pattern in EXCLUSIONS[exclusion])
