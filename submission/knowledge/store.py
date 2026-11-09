"""In-memory store: every snapshot, page, table row and prose passage, indexed by snapshot date.

Nothing is merged across snapshots. History *is* the set of snapshots, so an ``as_of`` question
simply reads a different snapshot's rows and pages.
"""
from __future__ import annotations

import re

from contract import Snapshot  # noqa: E402

from .authority import normal_url, page_rank
from .parsing import prose_chunks, table_rows
from .text import parse_date, tokenize


class SnapshotStore:
    def __init__(self):
        self.snapshots = []                 # [(snapshot_id, taken_on)], oldest first
        self.pages_by_snapshot = {}         # taken_on -> [page record]
        self.page_versions = {}             # normalised url -> [page record across snapshots]
        self.rows_by_snapshot = {}          # taken_on -> [table-row record]
        self.passages_by_snapshot = {}      # taken_on -> [prose-passage record]

    def ingest(self, snapshot: Snapshot) -> None:
        """Index a complete dated snapshot. The scorer calls these oldest first."""
        if self.snapshots and snapshot.taken_on < self.snapshots[-1][1]:
            raise ValueError("Snapshots must be ingested oldest first")
        self.snapshots.append((snapshot.snapshot_id, snapshot.taken_on))
        pages, rows, passages = [], [], []
        for page in snapshot.pages:
            record = {
                "url": page.url, "title": page.title, "text": page.markdown,
                "snapshot_id": snapshot.snapshot_id, "date": snapshot.taken_on,
                "rank": page_rank(page.url, page.title, page.markdown),
            }
            pages.append(record)
            self.page_versions.setdefault(normal_url(page.url), []).append(record)
            page_terms = tokenize(page.title + " " + page.url)
            for heading, row_text, cells in table_rows(page.markdown):
                row = dict(record)
                row.update(kind="table", heading=heading, body=row_text, cells=cells,
                           terms=tokenize(page.title + " " + page.url + " " + heading + " " + row_text))
                row["effective_date"] = parse_date(" ".join((heading, row_text, page.markdown[max(0, page.markdown.find(row_text)-180):page.markdown.find(row_text)+len(row_text)+500])))
                rows.append(row)
            for heading, body in prose_chunks(page.markdown):
                expired_match = re.search(r"offer ended\s+(\d{4}-\d{2}-\d{2})", body, re.I)
                passages.append({**record, "kind": "prose", "heading": heading,
                                 "body": body, "terms": tokenize(page.title + " " + page.url + " " + heading + " " + body),
                                 "page_terms": page_terms,
                                 "expired_on": expired_match.group(1) if expired_match else None})
        self.pages_by_snapshot[snapshot.taken_on] = pages
        self.rows_by_snapshot[snapshot.taken_on] = rows
        self.passages_by_snapshot[snapshot.taken_on] = passages

    def selected_date(self, as_of):
        """Latest snapshot date on or before ``as_of`` (the newest when ``as_of`` is empty)."""
        if not self.snapshots:
            return None
        if not as_of:
            return self.snapshots[-1][1]
        eligible = [d for _, d in self.snapshots if d <= as_of]
        return max(eligible) if eligible else None
