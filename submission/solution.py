"""Snapshot-grounded knowledge system (entry point).

The scorer calls ``build()`` and then ``ingest()`` / ``answer()`` / ``conflicts()``. All logic
lives in the ``knowledge`` package; see ``docs/ARCHITECTURE.md`` for the design.

Answer pipeline (``KnowledgeSystem.answer``):
    1. pick the snapshot for the requested date           (knowledge.dates, knowledge.store)
    2. decline unpublished rate / branch questions         (knowledge.handlers.decline)
    3. try the targeted handlers, first match wins         (knowledge.handlers)
    4. otherwise keyword retrieval with hard filters       (knowledge.retrieval)
"""
from __future__ import annotations

import sys
from pathlib import Path

# The harness provides the contract dataclasses (harness/contract.py) and this package's folder.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(next(
    d / "harness" for d in Path(__file__).resolve().parents
    if (d / "harness" / "contract.py").exists()
)))
from contract import Answer, Snapshot  # noqa: E402

from knowledge.conflicts import build_conflicts  # noqa: E402
from knowledge.dates import requested_date  # noqa: E402
from knowledge.handlers import HANDLERS, should_decline  # noqa: E402
from knowledge.retrieval import keyword_answer  # noqa: E402
from knowledge.store import SnapshotStore  # noqa: E402


class KnowledgeSystem:
    def __init__(self):
        self.store = SnapshotStore()
        self._conflicts = []

    def ingest(self, snapshot: Snapshot) -> None:
        """Index a complete dated snapshot (called oldest first) and refresh the conflict list."""
        self.store.ingest(snapshot)
        self._conflicts = build_conflicts(self.store)

    def answer(self, question: str, as_of=None) -> Answer:
        store = self.store
        if not store.snapshots:
            return Answer("I don't know; no snapshots are available.", confident=False)
        target = store.selected_date(requested_date(question, as_of))
        if target is None:
            return Answer("I don't have a website snapshot from that date, so I can't confirm.", confident=False)
        if should_decline(question, target, store):
            return Answer("The website doesn't list that information. Please contact a Dupaco lender or branch for help.", confident=False)
        for handler in HANDLERS:
            answer = handler(question, target, store)
            if answer is not None:
                return answer
        return keyword_answer(question, target, store)

    def conflicts(self):
        return list(self._conflicts)


def build():
    return KnowledgeSystem()
