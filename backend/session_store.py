"""SQLite-backed session, proposal, and upload storage."""

import json
import re
import secrets
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from .core.config import DATA_DIR, SESSION_TTL_SECONDS

SessionData = dict[str, Any]

DB_PATH = DATA_DIR / "app.sqlite3"
UPLOADS_DIR = DATA_DIR / "uploads"
SESSION_ID_RE = re.compile(r"^sess_[A-Za-z0-9_-]{16,}$")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_storage() -> None:
    """Create local storage folders and database tables."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                mode TEXT NOT NULL,
                kb_revision INTEGER NOT NULL DEFAULT 0,
                base_kb_json TEXT NOT NULL,
                current_kb_json TEXT NOT NULL,
                history_json TEXT NOT NULL,
                token_usage_total INTEGER NOT NULL DEFAULT 0,
                warnings_json TEXT NOT NULL,
                user_extraction_instruction TEXT NOT NULL DEFAULT '',
                ontology_file TEXT,
                query_file TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proposals (
                proposal_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                proposal_json TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_proposals_session_id ON proposals(session_id)")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def is_valid_session_id(session_id: Optional[str]) -> bool:
    return bool(isinstance(session_id, str) and SESSION_ID_RE.fullmatch(session_id.strip()))


def new_session_id() -> str:
    """Create a secure, URL-safe session id."""
    return f"sess_{secrets.token_urlsafe(24)}"


def session_upload_dir(session_id: str) -> Path:
    """Return a path-safe upload directory for a session."""
    if not is_valid_session_id(session_id):
        raise ValueError("Invalid session_id")
    base = UPLOADS_DIR.resolve()
    target = (UPLOADS_DIR / session_id).resolve()
    if base != target and base not in target.parents:
        raise ValueError("Invalid upload path")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _remove_upload_dir(session_id: str) -> None:
    if not is_valid_session_id(session_id):
        return
    base = UPLOADS_DIR.resolve()
    target = (UPLOADS_DIR / session_id).resolve()
    if base == target or base not in target.parents:
        return
    shutil.rmtree(target, ignore_errors=True)


def cleanup_expired_sessions() -> list[str]:
    """Delete expired sessions, their proposals, and their uploads."""
    init_storage()
    now = time.time()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT session_id FROM sessions WHERE expires_at <= ?",
            (now,),
        ).fetchall()
        expired_ids = [str(row["session_id"]) for row in rows]
        if expired_ids:
            conn.executemany("DELETE FROM sessions WHERE session_id = ?", [(sid,) for sid in expired_ids])
    for sid in expired_ids:
        _remove_upload_dir(sid)
    return expired_ids


def _row_to_session(row: sqlite3.Row) -> SessionData:
    return {
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "expires_at": row["expires_at"],
        "mode": row["mode"],
        "kb_revision": int(row["kb_revision"] or 0),
        "base_kb_json": _json_loads(row["base_kb_json"], []),
        "current_kb_json": _json_loads(row["current_kb_json"], []),
        "history": _json_loads(row["history_json"], []),
        "token_usage_total": int(row["token_usage_total"] or 0),
        "warnings": _json_loads(row["warnings_json"], []),
        "user_extraction_instruction": row["user_extraction_instruction"] or "",
        "ontology_file": row["ontology_file"],
        "query_file": row["query_file"],
    }


def get_session(session_id: Optional[str]) -> Optional[SessionData]:
    """Load a non-expired session by id."""
    init_storage()
    sid = (session_id or "").strip()
    if not is_valid_session_id(sid):
        return None
    cleanup_expired_sessions()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (sid,)).fetchone()
    return _row_to_session(row) if row else None


def create_session(
    *,
    mode: str,
    base_rows: list[dict[str, Any]],
    warnings: Optional[list[str]] = None,
) -> tuple[str, SessionData]:
    """Create and persist a new session."""
    init_storage()
    cleanup_expired_sessions()
    now = time.time()
    expires_at = now + SESSION_TTL_SECONDS
    session = {
        "created_at": now,
        "updated_at": now,
        "expires_at": expires_at,
        "mode": mode,
        "kb_revision": 0,
        "base_kb_json": base_rows,
        "current_kb_json": [dict(row) for row in base_rows],
        "history": [],
        "token_usage_total": 0,
        "warnings": warnings or [],
        "user_extraction_instruction": "",
        "ontology_file": None,
        "query_file": None,
    }
    while True:
        sid = new_session_id()
        try:
            save_session(sid, session)
            return sid, session
        except sqlite3.IntegrityError:
            continue


def save_session(session_id: str, session: SessionData) -> None:
    """Persist the complete session snapshot."""
    init_storage()
    if not is_valid_session_id(session_id):
        raise ValueError("Invalid session_id")
    now = time.time()
    created_at = float(session.get("created_at") or now)
    expires_at = float(session.get("expires_at") or (now + SESSION_TTL_SECONDS))
    session["updated_at"] = now
    session["expires_at"] = expires_at
    payload = {
        "session_id": session_id,
        "created_at": created_at,
        "updated_at": now,
        "expires_at": expires_at,
        "mode": str(session.get("mode") or "create_new"),
        "kb_revision": int(session.get("kb_revision") or 0),
        "base_kb_json": _json_dumps(session.get("base_kb_json") or []),
        "current_kb_json": _json_dumps(session.get("current_kb_json") or []),
        "history_json": _json_dumps(session.get("history") or []),
        "token_usage_total": int(session.get("token_usage_total") or 0),
        "warnings_json": _json_dumps(session.get("warnings") or []),
        "user_extraction_instruction": str(session.get("user_extraction_instruction") or ""),
        "ontology_file": session.get("ontology_file"),
        "query_file": session.get("query_file"),
    }
    with _connect() as conn:
        conn.execute("""
            INSERT INTO sessions (
                session_id, created_at, updated_at, expires_at, mode, kb_revision,
                base_kb_json, current_kb_json, history_json, token_usage_total,
                warnings_json, user_extraction_instruction, ontology_file, query_file
            ) VALUES (
                :session_id, :created_at, :updated_at, :expires_at, :mode, :kb_revision,
                :base_kb_json, :current_kb_json, :history_json, :token_usage_total,
                :warnings_json, :user_extraction_instruction, :ontology_file, :query_file
            )
            ON CONFLICT(session_id) DO UPDATE SET
                updated_at = excluded.updated_at,
                expires_at = excluded.expires_at,
                mode = excluded.mode,
                kb_revision = excluded.kb_revision,
                base_kb_json = excluded.base_kb_json,
                current_kb_json = excluded.current_kb_json,
                history_json = excluded.history_json,
                token_usage_total = excluded.token_usage_total,
                warnings_json = excluded.warnings_json,
                user_extraction_instruction = excluded.user_extraction_instruction,
                ontology_file = excluded.ontology_file,
                query_file = excluded.query_file
        """, payload)


def save_proposal(proposal: dict[str, Any]) -> None:
    """Persist a proposal linked to its owning session."""
    init_storage()
    proposal_id = str(proposal.get("proposal_id") or "").strip()
    session_id = str(proposal.get("session_id") or "").strip()
    if not proposal_id or not is_valid_session_id(session_id):
        raise ValueError("Proposal must include proposal_id and a valid session_id")
    created_at = float(proposal.get("created_at") or time.time())
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO proposals (proposal_id, session_id, created_at, proposal_json)
            VALUES (?, ?, ?, ?)
            """,
            (proposal_id, session_id, created_at, _json_dumps(proposal)),
        )


def get_proposal(session_id: str, proposal_id: str) -> Optional[dict[str, Any]]:
    """Load a proposal only when it belongs to the requested session."""
    init_storage()
    if not is_valid_session_id(session_id) or not proposal_id:
        return None
    cleanup_expired_sessions()
    with _connect() as conn:
        row = conn.execute(
            "SELECT proposal_json FROM proposals WHERE session_id = ? AND proposal_id = ?",
            (session_id, proposal_id),
        ).fetchone()
    if not row:
        return None
    proposal = _json_loads(row["proposal_json"], None)
    return proposal if isinstance(proposal, dict) else None


def delete_session_proposals(session_id: str) -> None:
    """Remove all proposals for one session."""
    init_storage()
    if not is_valid_session_id(session_id):
        return
    with _connect() as conn:
        conn.execute("DELETE FROM proposals WHERE session_id = ?", (session_id,))


def delete_all_sessions() -> None:
    """Remove all stored sessions, proposals, and uploads."""
    init_storage()
    with _connect() as conn:
        conn.execute("DELETE FROM sessions")
    if UPLOADS_DIR.exists():
        shutil.rmtree(UPLOADS_DIR, ignore_errors=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def count_sessions() -> int:
    init_storage()
    cleanup_expired_sessions()
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM sessions").fetchone()
    return int(row["count"] if row else 0)


def count_proposals() -> int:
    init_storage()
    cleanup_expired_sessions()
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM proposals").fetchone()
    return int(row["count"] if row else 0)
