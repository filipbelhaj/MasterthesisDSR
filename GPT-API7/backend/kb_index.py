import re
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Tuple

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]{3,}")

# session_id -> (kb_revision, sqlite_conn)
_INDEX_CACHE: Dict[str, Tuple[int, sqlite3.Connection]] = {}

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
    return " ".join(str(p) for p in parts if p is not None).replace("\n", " ").strip()

def _fts_query_from_text(text: str, max_tokens: int = 28) -> Optional[str]:
    if not text:
        return None
    tokens: List[str] = []
    seen = set()
    for tok in _TOKEN_RE.findall(text.lower()[:4000]):
        if tok in seen:
            continue
        seen.add(tok)
        tokens.append(tok)
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
        for idx, row in enumerate(rows):
            txt = _row_search_text(row)
            if not txt:
                continue
            payload.append((idx + 1, txt))
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
    cached = _INDEX_CACHE.get(session_id)
    if cached and cached[0] == kb_revision:
        return cached[1]
    if cached:
        try:
            cached[1].close()
        except Exception:
            pass
        _INDEX_CACHE.pop(session_id, None)
    conn = _build_conn(rows)
    if conn is None:
        return None
    _INDEX_CACHE[session_id] = (kb_revision, conn)
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
    q = _fts_query_from_text(input_text)
    if not q:
        return []
    try:
        cur = conn.execute(
            "SELECT rowid FROM kb_fts WHERE kb_fts MATCH ? ORDER BY bm25(kb_fts) LIMIT ?",
            (q, int(limit)),
        )
        # rowid was stored as (idx + 1)
        return [max(0, int(r[0]) - 1) for r in cur.fetchall() if r and r[0] is not None]
    except sqlite3.OperationalError:
        return []

