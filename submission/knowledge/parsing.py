"""Markdown parsing: table rows and prose passages."""
from __future__ import annotations

import re

from .text import TABLE_SEP_RE


def table_rows(markdown: str):
    """Yield (heading, row text, header/value mapping) from markdown tables."""
    lines = markdown.splitlines()
    heading = ""
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#"):
            heading = re.sub(r"^#+\s*", "", line).strip()
        if line.startswith("|") and i + 1 < len(lines) and TABLE_SEP_RE.match(lines[i + 1].strip()):
            headers = [c.strip() for c in line.strip("|").split("|")]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw = lines[i].strip()
                cells = [c.strip() for c in raw.strip("|").split("|")]
                if len(cells) == len(headers):
                    yield heading, raw, dict(zip(headers, cells))
                i += 1
            continue
        i += 1



def prose_chunks(markdown: str):
    """Split prose into compact heading-aware paragraphs."""
    heading = ""
    for block in re.split(r"\n\s*\n", markdown):
        block = block.strip()
        if not block:
            continue
        if block.startswith("#"):
            heading = re.sub(r"^#+\s*", "", block).strip()
            continue
        # Avoid giant pages/captured navigational sections as a single retrieval unit.
        if len(block) > 1600:
            for piece in re.split(r"(?<=[.!?])\s+", block):
                if len(piece.strip()) > 35:
                    yield heading, piece.strip()[:800]
        elif len(block) > 12:
            yield heading, block[:1200]
