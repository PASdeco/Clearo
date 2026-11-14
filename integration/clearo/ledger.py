"""Clearo's settlement ledger: an append-only record of real events.

One JSON object per line in <data_dir>/settlement-ledger.jsonl. Entries are
written when something actually happens: an invoice is created, a status
changes, a fee is verified or a mismatch is found. Nothing is backfilled
and nothing is padded; this file is the book our published numbers must
match.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

LEDGER_NAME = "settlement-ledger.jsonl"


def append_event(data_dir: str | Path, event_type: str, **fields) -> dict:
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "type": event_type, **fields}
    path = Path(data_dir) / LEDGER_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def read_events(data_dir: str | Path) -> list[dict]:
    path = Path(data_dir) / LEDGER_NAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
