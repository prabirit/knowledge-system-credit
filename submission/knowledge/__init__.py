"""Knowledge-system package: ingestion, routing, answer handlers, retrieval and conflicts.

The scorer's contract dataclasses (``contract.py``) live in the repository's ``harness/`` folder.
Making them importable here means this package works no matter which module imports it first.
"""
import sys
from pathlib import Path

_HARNESS = next(
    (d / "harness" for d in Path(__file__).resolve().parents if (d / "harness" / "contract.py").exists()),
    None,
)
if _HARNESS is not None and str(_HARNESS) not in sys.path:
    sys.path.insert(0, str(_HARNESS))
