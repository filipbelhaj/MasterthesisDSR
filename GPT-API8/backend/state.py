import json
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from .core.config import DEFAULT_QUERY_FILE, FTS_QUERY_MAX_TOKENS

SESSIONS: Dict[str, Dict[str, Any]] = {}
PROPOSALS: Dict[str, Dict[str, Any]] = {}

ROW_ID_KEYS = ["item", "property", "value", "qualifierProperty", "qualifierValue"]
SESSION_MODES = ("create_new", "extend_existing")
TOKEN_RE = re.compile(r"[A-Za-z0-9_]{3,}")

INDEX_CACHE: Dict[str, Tuple[int, sqlite3.Connection]] = {}

def default_session_mode() -> str:
    return "extend_existing" if DEFAULT_QUERY_FILE.exists() else "create_new"

def normalize_session_mode(mode: Optional[str]) -> str:
    if not mode:
        return default_session_mode()
    mode_norm = str(mode).strip()
    return mode_norm if mode_norm in SESSION_MODES else default_session_mode()

def normalize_key_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    cleaned = " ".join(value.split())
    if cleaned == "":
        return None
    return cleaned.casefold()

def load_json_file(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))

def norm(value: Optional[str]) -> str:
    return " ".join((value or "").lower().split())

def new_session_id() -> str:
    return f"sess_{uuid.uuid4().hex[:12]}"

def _row_dicts(rows: Any) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

def get_or_create_session(session_id: Optional[str], mode: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    sid = (session_id or "").strip() or new_session_id()
    if sid in SESSIONS:
        return sid, SESSIONS[sid]

    resolved_mode = normalize_session_mode(mode)
    loaded_rows: Any = []
    if resolved_mode == "extend_existing" and DEFAULT_QUERY_FILE.exists():
        try:
            loaded_rows = load_json_file(DEFAULT_QUERY_FILE)
        except Exception:
            pass

    base_rows_clean = _row_dicts(loaded_rows)
    session = {
        "created_at": time.time(),
        "mode": resolved_mode,
        "kb_revision": 0,
        "base_kb_json": base_rows_clean,
        "current_kb_json": [dict(row) for row in base_rows_clean],
        "token_usage_total": 0,
        "history": [],
    }
    SESSIONS[sid] = session
    return sid, session

def canonical_row_key(row: Dict[str, Any]) -> Tuple[Any, ...]:
    return tuple(normalize_key_value(row.get(key)) for key in ROW_ID_KEYS)

def dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for row in rows:
        key = canonical_row_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out

def rows_delta(base_rows: List[Dict[str, Any]], current_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    base_keys = {canonical_row_key(row) for row in base_rows if isinstance(row, dict)}
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in current_rows:
        if not isinstance(row, dict):
            continue
        key = canonical_row_key(row)
        if key in base_keys or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out

def rows_removed(base_rows: List[Dict[str, Any]], current_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    current_keys = {canonical_row_key(row) for row in current_rows if isinstance(row, dict)}
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in base_rows:
        if not isinstance(row, dict):
            continue
        key = canonical_row_key(row)
        if key in current_keys or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out

def _row_search_text(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    parts = [
        row.get("itemLabel") or row.get("item"),
        row.get("propertyLabel") or row.get("property"),
        row.get("valueLabel") or row.get("value"),
        row.get("qualifierPropertyLabel") or row.get("qualifierProperty"),
        row.get("qualifierValueLabel") or row.get("qualifierValue"),
    ]
    return " ".join(str(part) for part in parts if part is not None).replace("\n", " ").strip()

def _fts_query_from_text(text: str, max_tokens: int = FTS_QUERY_MAX_TOKENS) -> Optional[str]:
    if not text:
        return None
    tokens: List[str] = []
    seen = set()
    for token in TOKEN_RE.findall(text.lower()[:4000]):
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
        if len(tokens) >= max_tokens:
            break
    if not tokens:
        return None
    return " OR ".join(tokens)

def _build_conn(rows: List[Any]) -> Optional[sqlite3.Connection]:
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("CREATE VIRTUAL TABLE kb_fts USING fts5(text)")
        payload: List[Tuple[int, str]] = []
        for index, row in enumerate(rows):
            text = _row_search_text(row)
            if not text:
                continue
            payload.append((index + 1, text))
        conn.executemany("INSERT INTO kb_fts(rowid, text) VALUES (?, ?)", payload)
        return conn
    except Exception:
        try:
            conn.close()  # type: ignore[misc]
        except Exception:
            pass
        return None

def get_or_build_index(session_id: Optional[str], kb_revision: int, rows: List[Any]) -> Optional[sqlite3.Connection]:
    if not session_id:
        return None
    cached = INDEX_CACHE.get(session_id)
    if cached and cached[0] == kb_revision:
        return cached[1]
    if cached:
        try:
            cached[1].close()
        except Exception:
            pass
        INDEX_CACHE.pop(session_id, None)
    conn = _build_conn(rows)
    if conn is None:
        return None
    INDEX_CACHE[session_id] = (kb_revision, conn)
    return conn

def fts_candidate_indices(
    session_id: Optional[str],
    kb_revision: int,
    rows: List[Any],
    input_text: str,
    limit: int,
) -> List[int]:
    conn = get_or_build_index(session_id=session_id, kb_revision=kb_revision, rows=rows)
    if conn is None:
        return []
    query = _fts_query_from_text(input_text)
    if not query:
        return []
    try:
        cur = conn.execute(
            "SELECT rowid FROM kb_fts WHERE kb_fts MATCH ? ORDER BY bm25(kb_fts) LIMIT ?",
            (query, int(limit)),
        )
        return [max(0, int(row[0]) - 1) for row in cur.fetchall() if row and row[0] is not None]
    except sqlite3.OperationalError:
        return []

def clear_index_cache() -> None:
    for _, conn in list(INDEX_CACHE.values()):
        try:
            conn.close()
        except Exception:
            pass
    INDEX_CACHE.clear()