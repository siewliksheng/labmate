"""M2/M4: lab memory, and the experiment-session state M4 adds on top.

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

M4 note: qa_history and image_analyses gained a nullable experiment_id
column so a Report (see labmate.experiment) can pull back everything tied
to one experiment session. If you have a var/labmate_memory.db from
before M4, delete it (the whole var/ directory is disposable local state,
never committed) -- there's no migration story for a local dev SQLite
file, which is a deliberate scope cut, not an oversight.

Local-state convention shared with escalate_to_safety_officer (tools.py):
get_active_experiment_id()/set_active_experiment_id() track "which
experiment is currently open" via a small file in VAR_DIR, so ad-hoc Lab
questions through agent.run() get tagged automatically without the user
threading an experiment_id through every call.
"""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from labmate.paths import VAR_DIR

_ACTIVE_EXPERIMENT_POINTER = "active_experiment.json"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS qa_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    specialist TEXT NOT NULL,
    user_input TEXT NOT NULL,
    response_text TEXT NOT NULL,
    experiment_id TEXT
);

CREATE TABLE IF NOT EXISTS image_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    image_path TEXT NOT NULL,
    description TEXT NOT NULL,
    hazard_scan_findings TEXT NOT NULL,
    human_label TEXT,
    experiment_id TEXT
);

CREATE TABLE IF NOT EXISTS environmental_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bench TEXT NOT NULL,
    description TEXT NOT NULL,
    logged_by TEXT NOT NULL,
    logged_at TEXT NOT NULL,
    ttl_hours REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    prelab_checklist TEXT,
    signed_off_by TEXT,
    signed_off_at TEXT
);

CREATE TABLE IF NOT EXISTS lab_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    note TEXT
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


def record_qa(specialist: str, user_input: str, response_text: str, experiment_id: str | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO qa_history (timestamp, specialist, user_input, response_text, experiment_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), specialist, user_input, response_text, experiment_id),
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


def get_qa_history_for_experiment(experiment_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT timestamp, specialist, user_input, response_text FROM qa_history "
            "WHERE experiment_id = ? ORDER BY id",
            (experiment_id,),
        ).fetchall()
    return [dict(row) for row in rows]


# --- Image analysis history ---------------------------------------------


def record_image_analysis(
    image_path: str,
    description: str,
    hazard_scan_findings: str,
    human_label: str | None = None,
    experiment_id: str | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO image_analyses "
            "(timestamp, image_path, description, hazard_scan_findings, human_label, experiment_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                image_path,
                description,
                hazard_scan_findings,
                human_label,
                experiment_id,
            ),
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


# --- Experiment sessions (M4) --------------------------------------------


def create_experiment(description: str) -> str:
    experiment_id = uuid.uuid4().hex[:8]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO experiments (id, created_at, description, status) VALUES (?, ?, ?, ?)",
            (experiment_id, datetime.now(timezone.utc).isoformat(), description, "prelab_pending"),
        )
    set_active_experiment_id(experiment_id)
    return experiment_id


def get_experiment(experiment_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
    return dict(row) if row else None


def save_prelab_checklist(experiment_id: str, checklist: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE experiments SET prelab_checklist = ?, status = ? WHERE id = ?",
            (json.dumps(checklist), "prelab_ready", experiment_id),
        )


def sign_off_experiment(experiment_id: str, signed_off_by: str, acknowledge_unresolved: bool = False) -> dict:
    experiment = get_experiment(experiment_id)
    if experiment is None:
        return {"signed_off": False, "note": f"No experiment with id {experiment_id}"}

    checklist = json.loads(experiment["prelab_checklist"] or "{}")
    unresolved_items = [item for item in checklist.get("items", []) if not item.get("resolved")]

    if unresolved_items and not acknowledge_unresolved:
        return {
            "signed_off": False,
            "note": f"{len(unresolved_items)} unresolved prelab item(s) must be acknowledged before lab work starts.",
            "unresolved_items": unresolved_items,
        }

    with _connect() as conn:
        conn.execute(
            "UPDATE experiments SET status = ?, signed_off_by = ?, signed_off_at = ? WHERE id = ?",
            ("lab", signed_off_by, datetime.now(timezone.utc).isoformat(), experiment_id),
        )
    return {"signed_off": True, "unresolved_acknowledged": len(unresolved_items)}


def mark_experiment_reported(experiment_id: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE experiments SET status = ? WHERE id = ?", ("reported", experiment_id))


def record_lab_observation(experiment_id: str, kind: str, content: str, note: str | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO lab_observations (experiment_id, timestamp, kind, content, note) VALUES (?, ?, ?, ?, ?)",
            (experiment_id, datetime.now(timezone.utc).isoformat(), kind, content, note),
        )


def get_lab_observations(experiment_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT timestamp, kind, content, note FROM lab_observations WHERE experiment_id = ? ORDER BY id",
            (experiment_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_active_experiment_id() -> str | None:
    path = VAR_DIR / _ACTIVE_EXPERIMENT_POINTER
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("experiment_id")
    except Exception:
        return None


def set_active_experiment_id(experiment_id: str | None) -> None:
    VAR_DIR.mkdir(exist_ok=True, parents=True)
    path = VAR_DIR / _ACTIVE_EXPERIMENT_POINTER
    if experiment_id is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(json.dumps({"experiment_id": experiment_id}), encoding="utf-8")
