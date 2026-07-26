"""M2: lab memory.

SQLite locally (var/labmate_memory.db, never committed) rather than the
Postgres + pgvector the README's "Stack" section names as the eventual
production backend -- standing up real Postgres for a portfolio demo isn't
justified yet, and swapping it in later only touches this module, not its
callers.

Retrieval here is keyword-based (SQL LIKE), not embedding-based. Adding an
embeddings dependency -- and the API key/service that comes with it --
isn't justified until there's a concrete recall failure this doesn't
solve; see docs/architecture.md for the general principle.

Write policy: every completed exchange is recorded automatically. The
model is never asked "was this worth remembering?" -- letting it decide
adds a real failure mode (skipping something important) without a proven
benefit. Retrieval precision is handled at read time (ranking + limit),
not by being selective about writes.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from labmate.paths import VAR_DIR

_SCHEMA = """
CREATE TABLE IF NOT EXISTS qa_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    specialist TEXT NOT NULL,
    user_input TEXT NOT NULL,
    response_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS image_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    image_path TEXT NOT NULL,
    description TEXT NOT NULL,
    hazard_scan_findings TEXT NOT NULL,
    human_label TEXT
);

CREATE TABLE IF NOT EXISTS environmental_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bench TEXT NOT NULL,
    description TEXT NOT NULL,
    logged_by TEXT NOT NULL,
    logged_at TEXT NOT NULL,
    ttl_hours REAL NOT NULL
);
"""


@contextmanager
def _connect():
    # VAR_DIR is read here, not at import time, so tests can monkeypatch
    # labmate.memory.store.VAR_DIR to an isolated tmp_path per test.
    VAR_DIR.mkdir(exist_ok=True, parents=True)
    conn = sqlite3.connect(VAR_DIR / "labmate_memory.db")
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _like_clause(columns: list[str], terms: list[str]) -> tuple[str, list[str]]:
    if not terms:
        return "1=1", []
    conditions = []
    params = []
    for term in terms:
        conditions.append("(" + " OR ".join(f"{col} LIKE ?" for col in columns) + ")")
        params.extend([f"%{term}%"] * len(columns))
    return " AND ".join(conditions), params


# --- Q&A history -------------------------------------------------------


def record_qa(specialist: str, user_input: str, response_text: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO qa_history (timestamp, specialist, user_input, response_text) VALUES (?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), specialist, user_input, response_text),
        )


def search_past_qa(query: str, max_results: int = 5):
    terms = query.lower().split()
    where, params = _like_clause(["LOWER(user_input)", "LOWER(response_text)"], terms)
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT timestamp, specialist, user_input, response_text FROM qa_history "
            f"WHERE {where} ORDER BY id DESC LIMIT ?",
            (*params, max_results),
        ).fetchall()

    results = [dict(row) for row in rows]
    if not results:
        return {"results": [], "note": "No past Q&A matched this query."}
    return {"results": results}


# --- Image analysis history ---------------------------------------------


def record_image_analysis(
    image_path: str, description: str, hazard_scan_findings: str, human_label: str | None = None
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO image_analyses (timestamp, image_path, description, hazard_scan_findings, human_label) "
            "VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), image_path, description, hazard_scan_findings, human_label),
        )


def search_past_image_analyses(query: str, max_results: int = 5):
    terms = query.lower().split()
    where, params = _like_clause(
        ["LOWER(description)", "LOWER(hazard_scan_findings)", "LOWER(COALESCE(human_label, ''))"], terms
    )
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT timestamp, image_path, description, hazard_scan_findings, human_label FROM image_analyses "
            f"WHERE {where} ORDER BY id DESC LIMIT ?",
            (*params, max_results),
        ).fetchall()

    results = [dict(row) for row in rows]
    if not results:
        return {"results": [], "note": "No past image analyses matched this query."}
    return {"results": results}


# --- Environmental state -------------------------------------------------


def log_environmental_state(bench: str, description: str, logged_by: str, ttl_hours: float = 2.0):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO environmental_state (bench, description, logged_by, logged_at, ttl_hours) "
            "VALUES (?, ?, ?, ?, ?)",
            (bench, description, logged_by, datetime.now(timezone.utc).isoformat(), ttl_hours),
        )
    return {"logged": True, "bench": bench, "ttl_hours": ttl_hours}


def get_environmental_state(bench: str):
    with _connect() as conn:
        row = conn.execute(
            "SELECT description, logged_by, logged_at, ttl_hours FROM environmental_state "
            "WHERE bench = ? ORDER BY id DESC LIMIT 1",
            (bench,),
        ).fetchone()

    if row is None:
        return {
            "found": False,
            "bench": bench,
            "reason": "no environmental state has ever been logged for this bench",
        }

    logged_at = datetime.fromisoformat(row["logged_at"])
    expires_at = logged_at + timedelta(hours=row["ttl_hours"])
    if datetime.now(timezone.utc) > expires_at:
        return {
            "found": False,
            "bench": bench,
            "reason": "expired",
            "note": "The last logged state expired -- treat as unknown, not as the last-known value.",
            "last_known_at": row["logged_at"],
        }

    return {
        "found": True,
        "bench": bench,
        "description": row["description"],
        "logged_by": row["logged_by"],
        "logged_at": row["logged_at"],
        "expires_at": expires_at.isoformat(),
    }
