"""Targeted answer handlers, one module per fact type.

Each handler is a function (question, target, store) -> Answer or None. It reads its value from
the matching page or table row in the selected snapshot and returns None when the question is
not its kind of question.
"""
from .branches import answer_branch_or_checking
from .decline import should_decline
from .facts import answer_general_fact
from .mortgage import answer_mortgage_rate
from .products import answer_product_list
from .rates import answer_rate_lookup

# Order matters: the first handler that returns an answer wins.
HANDLERS = (
    answer_rate_lookup,
    answer_branch_or_checking,
    answer_mortgage_rate,
    answer_product_list,
    answer_general_fact,
)

__all__ = ["HANDLERS", "should_decline"]
