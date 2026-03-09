import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from .config import DEFAULT_QUERY_FILE

SESSIONS: Dict[str, Dict[str, Any]] = {}
PROPOSALS: Dict[str, Dict[str, Any]] = {}

ROW_ID_KEYS = ["item", "property", "value", "qualifierProperty", "qualifierValue"]

def normalize_key_value(value: Any) -> Any:
    return " ".join(value.split()).casefold() if isinstance(value, str) else value

def load_json_file(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))

def norm(s: Optional[str]) -> str:
    return " ".join((s or "").lower().split())

def new_session_id() -> str:
    return f"sess_{uuid.uuid4().hex[:12]}"

def _row_dicts(rows: Any) -> List[Dict[str, Any]]:
    return [dict(r) for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []

def get_or_create_session(session_id: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    sid = (session_id or "").strip() or new_session_id()
    if sid in SESSIONS:
        return sid, SESSIONS[sid]

    loaded_rows: Any = []
    if DEFAULT_QUERY_FILE.exists():
        try:
            loaded_rows = load_json_file(DEFAULT_QUERY_FILE)
        except Exception:
            pass

    base_rows_clean = _row_dicts(loaded_rows)
    session = {
        "created_at": time.time(),
        "base_kb_json": base_rows_clean,
        "current_kb_json": [dict(r) for r in base_rows_clean],
        "history": [],
    }
    SESSIONS[sid] = session
    return sid, session

def canonical_row_key(row: Dict[str, Any]) -> Tuple[Any, ...]:
    return tuple(normalize_key_value(row.get(k)) for k in ROW_ID_KEYS)

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
    base_keys = {canonical_row_key(r) for r in base_rows if isinstance(r, dict)}
    out: List[Dict[str, Any]] = []
    seen = set()
    for r in current_rows:
        if not isinstance(r, dict):
            continue
        k = canonical_row_key(r)
        if k in base_keys or k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out