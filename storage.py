"""SQLite storage: content, appeals, certificates, and the append-only audit log."""

import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.environ.get("PROVENANCE_DB", "provenance.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS content (
    content_id TEXT PRIMARY KEY,
    creator_id TEXT NOT NULL,
    content_type TEXT NOT NULL,
    text TEXT NOT NULL,
    metadata_json TEXT,
    word_count INTEGER NOT NULL,
    ai_score REAL NOT NULL,
    confidence REAL NOT NULL,
    attribution TEXT NOT NULL,
    signals_json TEXT NOT NULL,
    votes_json TEXT NOT NULL,
    adjustments_json TEXT NOT NULL,
    label TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS appeals (
    appeal_id TEXT PRIMARY KEY,
    content_id TEXT NOT NULL REFERENCES content(content_id),
    creator_id TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS certificate_challenges (
    challenge_id TEXT PRIMARY KEY,
    creator_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS certificates (
    certificate_id TEXT PRIMARY KEY,
    creator_id TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    verification_score REAL NOT NULL,
    signature TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event TEXT NOT NULL,
    content_id TEXT,
    creator_id TEXT NOT NULL,
    details_json TEXT NOT NULL
);
"""


def utc_now():
    """UTC ISO-8601 timestamp with milliseconds, e.g. 2026-10-05T22:50:00.123Z."""
    return to_iso(datetime.now(timezone.utc))


def to_iso(dt):
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def from_iso(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript(SCHEMA)


# Content -------------------------------------------------------------------

def save_content(record):
    """Insert a classified content record. `record` matches the /submit response plus `text`."""
    with _connect() as conn:
        conn.execute(
            """INSERT INTO content (content_id, creator_id, content_type, text, metadata_json, word_count,
               ai_score, confidence, attribution, signals_json, votes_json, adjustments_json, label, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["content_id"],
                record["creator_id"],
                record["content_type"],
                record["text"],
                json.dumps(record["metadata"]) if record.get("metadata") is not None else None,
                record["word_count"],
                record["ai_score"],
                record["confidence"],
                record["attribution"],
                json.dumps(record["signals"]),
                json.dumps(record["votes"]),
                json.dumps(record["adjustments"]),
                record["label"],
                record["status"],
                record["created_at"],
            ),
        )


def _content_from_row(row):
    record = dict(row)
    metadata_json = record.pop("metadata_json")
    record["metadata"] = json.loads(metadata_json) if metadata_json else None
    record["signals"] = json.loads(record.pop("signals_json"))
    record["votes"] = json.loads(record.pop("votes_json"))
    record["adjustments"] = json.loads(record.pop("adjustments_json"))
    return record


def get_content(content_id):
    """Return a content record as a dict, or None if it does not exist."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM content WHERE content_id = ?", (content_id,)).fetchone()
    return _content_from_row(row) if row else None


def all_content():
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM content").fetchall()
    return [_content_from_row(r) for r in rows]


# Appeals -------------------------------------------------------------------

def get_appeal_for_content(content_id):
    """Return the most recent appeal for a content item, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM appeals WHERE content_id = ? ORDER BY created_at DESC LIMIT 1", (content_id,)
        ).fetchone()
    return dict(row) if row else None


def create_appeal(appeal, audit_details):
    """Record an appeal, set the content to under_review, and log it, in one transaction.

    The status check in the UPDATE makes this safe against two concurrent appeals:
    only one can move the content out of 'classified'. Returns False if the content
    was not in 'classified' state.
    """
    with _connect() as conn:
        updated = conn.execute(
            "UPDATE content SET status = 'under_review' WHERE content_id = ? AND status = 'classified'",
            (appeal["content_id"],),
        ).rowcount
        if updated == 0:
            return False
        conn.execute(
            "INSERT INTO appeals (appeal_id, content_id, creator_id, reasoning, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                appeal["appeal_id"],
                appeal["content_id"],
                appeal["creator_id"],
                appeal["reasoning"],
                appeal["status"],
                appeal["created_at"],
            ),
        )
        conn.execute(
            "INSERT INTO audit_log (timestamp, event, content_id, creator_id, details_json) VALUES (?, ?, ?, ?, ?)",
            (appeal["created_at"], "appeal", appeal["content_id"], appeal["creator_id"], json.dumps(audit_details)),
        )
    return True


def list_appeals(status="pending"):
    """Return (appeal, content) pairs with the given appeal status, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM appeals WHERE status = ? ORDER BY created_at ASC", (status,)
        ).fetchall()
    return [(dict(row), get_content(row["content_id"])) for row in rows]


def all_appeals():
    with _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM appeals").fetchall()]


# Certificates --------------------------------------------------------------

def save_challenge(challenge):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO certificate_challenges (challenge_id, creator_id, prompt, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (challenge["challenge_id"], challenge["creator_id"], challenge["prompt"], challenge["created_at"], challenge["expires_at"]),
        )


def get_challenge(challenge_id):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM certificate_challenges WHERE challenge_id = ?", (challenge_id,)).fetchone()
    return dict(row) if row else None


def consume_challenge(challenge_id):
    """Mark a challenge used. Returns False if it was already used (safe under concurrency)."""
    with _connect() as conn:
        return conn.execute(
            "UPDATE certificate_challenges SET used = 1 WHERE challenge_id = ? AND used = 0", (challenge_id,)
        ).rowcount == 1


def save_certificate(cert):
    with _connect() as conn:
        conn.execute(
            """INSERT INTO certificates (certificate_id, creator_id, issued_at, expires_at, verification_score, signature)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cert["certificate_id"], cert["creator_id"], cert["issued_at"], cert["expires_at"], cert["verification_score"], cert["signature"]),
        )


def get_certificate(certificate_id):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM certificates WHERE certificate_id = ?", (certificate_id,)).fetchone()
    return dict(row) if row else None


def latest_certificate_for(creator_id):
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM certificates WHERE creator_id = ? ORDER BY issued_at DESC LIMIT 1", (creator_id,)
        ).fetchone()
    return dict(row) if row else None


# Audit log -----------------------------------------------------------------

def append_audit(event, content_id, creator_id, details, timestamp=None):
    """Append one audit entry. The log is never updated or deleted."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (timestamp, event, content_id, creator_id, details_json) VALUES (?, ?, ?, ?, ?)",
            (timestamp or utc_now(), event, content_id, creator_id, json.dumps(details)),
        )


def count_events():
    """Return {event: count} over the whole audit log."""
    with _connect() as conn:
        rows = conn.execute("SELECT event, COUNT(*) AS n FROM audit_log GROUP BY event").fetchall()
    return {r["event"]: r["n"] for r in rows}


def get_log(limit=50, event=None):
    """Return audit entries newest first, with details flattened into each entry."""
    query = "SELECT * FROM audit_log"
    params = []
    if event:
        query += " WHERE event = ?"
        params.append(event)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()

    entries = []
    for row in rows:
        entry = {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "event": row["event"],
            "content_id": row["content_id"],
            "creator_id": row["creator_id"],
        }
        entry.update(json.loads(row["details_json"]))
        entries.append(entry)
    return entries
