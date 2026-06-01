"""In-memory session state, JSON loading helpers, and lightweight retrieval indexing."""

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional
from .core.config import DEFAULT_QUERY_FILE, FTS_QUERY_MAX_TOKENS
from .session_store import (
    create_session,
    get_session,
    new_session_id,
    save_session,
)

LOGGER = logging.getLogger(__name__)

Row = dict[str, Any]
SessionData = dict[str, Any]
ReferenceKey = tuple[Any, Any]
RowKey = tuple[Any, ...]

ROW_ID_KEYS: list[str] = ["item", "property", "value", "qualifierProperty", "qualifierValue"]
SESSION_MODES: tuple[str, str] = ("create_new", "extend_existing")
TOKEN_RE = re.compile(r"(?u)\w{3,}")
JSON_FALLBACK_ENCODINGS: tuple[str, ...] = (
    "utf-8-sig",
    "utf-16",
    "utf-16-le",
    "utf-16-be",
    "utf-32",
    "utf-32-le",
    "utf-32-be",
    "cp1252",
    "latin-1",
)

INDEX_CACHE: dict[str, tuple[int, sqlite3.Connection]] = {}

def default_session_mode() -> str:
    """Return the default session mode for new sessions.

    Returns:
        The mode based on whether a default query file exists.
    """
    return "extend_existing" if DEFAULT_QUERY_FILE.exists() else "create_new"

def normalize_session_mode(mode: Optional[str]) -> str:
    """Normalize a requested session mode.

    Args:
        mode: Requested session mode from the caller.

    Returns:
        A valid session mode, or the default when missing or invalid.
    """
    if not mode:
        return default_session_mode()
    mode_norm = str(mode).strip()
    return mode_norm if mode_norm in SESSION_MODES else default_session_mode()

def normalize_key_value(value: Any) -> Any:
    """Normalize a row key component for stable comparisons.

    Args:
        value: Raw row value to normalize.

    Returns:
        A folded string, `None` for empty strings, or the original value.
    """
    if not isinstance(value, str):
        return value
    cleaned = " ".join(value.split())
    if cleaned == "":
        return None
    return cleaned.casefold()

def parse_json_bytes(raw: bytes) -> Any:
    """Parse JSON bytes with a few fallback encodings.

    Args:
        raw: Raw JSON payload bytes.

    Returns:
        The decoded JSON value.
    """
    if isinstance(raw, bytearray):
        raw = bytes(raw)
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        last_error: Exception = exc

    # User-edited exports can come back in a few encodings, so retry before turning
    # a recoverable decode mismatch into a hard upload error.
    for encoding in JSON_FALLBACK_ENCODINGS:
        try:
            return json.loads(raw.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            last_error = exc

    raise last_error

def load_json_file(path: Path) -> Any:
    """Load and parse a JSON file from disk.

    Args:
        path: File path to read.

    Returns:
        The parsed JSON value.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    return parse_json_bytes(path.read_bytes())

def load_default_query_rows(
    *,
    load_failed_message: Optional[str] = None,
    invalid_message: Optional[str] = None,
) -> tuple[list[Row], list[str]]:
    """Load the default query rows when available.

    Args:
        load_failed_message: Warning to return if loading fails.
        invalid_message: Warning to return if the file is not a JSON array.

    Returns:
        Cleaned row dicts and any warning messages for the caller.
    """
    if not DEFAULT_QUERY_FILE.exists():
        return [], []

    try:
        loaded_rows = load_json_file(DEFAULT_QUERY_FILE)
    except Exception:
        LOGGER.exception("Failed to load default query rows from %s.", DEFAULT_QUERY_FILE)
        return [], [load_failed_message] if load_failed_message else []

    if not isinstance(loaded_rows, list):
        LOGGER.warning("%s must be a JSON array when used as the default query.", DEFAULT_QUERY_FILE.name)
        return [], [invalid_message] if invalid_message else []

    return _row_dicts(loaded_rows), []

def norm(value: Optional[str]) -> str:
    """Normalize text for case-insensitive matching.

    Args:
        value: Raw text value.

    Returns:
        Whitespace-collapsed, casefolded text.
    """
    return " ".join((value or "").casefold().split())

def _row_dicts(rows: Any) -> list[Row]:
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

def append_session_warning(session: SessionData, message: str) -> None:
    """Add a warning message to a session once.

    Args:
        session: Session data to update.
        message: Warning message to append.

    Returns:
        None.
    """
    if not message:
        return
    warnings = session.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
        session["warnings"] = warnings
    if message not in warnings:
        warnings.append(message)

def session_warnings(session: Optional[SessionData]) -> list[str]:
    """Return normalized warning strings from a session.

    Args:
        session: Session data to inspect.

    Returns:
        Warning messages stored on the session.
    """
    if not isinstance(session, dict):
        return []
    warnings = session.get("warnings")
    return [warning for warning in warnings if isinstance(warning, str)] if isinstance(warnings, list) else []

def get_or_create_session(session_id: Optional[str], mode: Optional[str] = None) -> tuple[str, SessionData]:
    """Fetch an existing session or initialize a new one.

    Args:
        session_id: Requested session id, if any.
        mode: Requested session mode.

    Returns:
        The resolved session id and session data.
    """
    sid = (session_id or "").strip() or new_session_id()
    existing_session = get_session(sid)
    if existing_session is not None:
        return sid, existing_session

    resolved_mode = normalize_session_mode(mode)
    base_rows_clean: list[Row] = []
    session_warning_messages: list[str] = []
    if resolved_mode == "extend_existing":
        base_rows_clean, session_warning_messages = load_default_query_rows(
            load_failed_message=f"Failed to load {DEFAULT_QUERY_FILE.name}; this session started with an empty base KB.",
            invalid_message=f"Ignored {DEFAULT_QUERY_FILE.name} for this session because it is not a JSON array.",
        )

    return create_session(
        mode=resolved_mode,
        base_rows=base_rows_clean,
        warnings=session_warning_messages,
    )

def canonical_row_key(row: Row) -> RowKey:
    """Build a canonical key for a knowledge-graph row.

    Args:
        row: Statement row to key.

    Returns:
        A normalized tuple used for deduping and diffing.
    """
    return tuple(normalize_key_value(row.get(key)) for key in ROW_ID_KEYS)

def _canonical_reference_key(reference: Row) -> ReferenceKey:
    return (
        normalize_key_value(reference.get("property")),
        normalize_key_value(reference.get("value")),
    )

def _merge_row_metadata(existing: Row, incoming: Row) -> None:
    for key, value in incoming.items():
        if key == "references":
            existing_refs = existing.get("references")
            if not isinstance(existing_refs, list):
                existing_refs = []
                existing["references"] = existing_refs

            seen = {
                _canonical_reference_key(reference)
                for reference in existing_refs
                if isinstance(reference, dict)
            }
            for reference in value if isinstance(value, list) else []:
                if not isinstance(reference, dict):
                    continue
                ref_key = _canonical_reference_key(reference)
                if ref_key in seen:
                    continue
                seen.add(ref_key)
                existing_refs.append(dict(reference))
            continue

        if existing.get(key) is None and value is not None:
            existing[key] = value

def dedupe_rows(rows: list[Row]) -> list[Row]:
    """Deduplicate rows while merging compatible metadata.

    Args:
        rows: Rows to deduplicate.

    Returns:
        Deduplicated rows in original order.
    """
    seen: dict[RowKey, Row] = {}
    out: list[Row] = []
    for row in rows:
        key = canonical_row_key(row)
        existing = seen.get(key)
        if existing is not None:
            _merge_row_metadata(existing, row)
            continue
        cloned = dict(row)
        references = cloned.get("references")
        if isinstance(references, list):
            cloned["references"] = [dict(reference) for reference in references if isinstance(reference, dict)]
        seen[key] = cloned
        out.append(cloned)
    return out

def rows_delta(base_rows: list[Row], current_rows: list[Row]) -> list[Row]:
    """Return rows added relative to a base snapshot.

    Args:
        base_rows: Starting rows for the session.
        current_rows: Current session rows.

    Returns:
        Rows present only in the current set.
    """
    base_keys = {canonical_row_key(row) for row in base_rows if isinstance(row, dict)}
    out: list[Row] = []
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

def rows_removed(base_rows: list[Row], current_rows: list[Row]) -> list[Row]:
    """Return rows removed relative to a base snapshot.

    Args:
        base_rows: Starting rows for the session.
        current_rows: Current session rows.

    Returns:
        Rows present only in the base set.
    """
    current_keys = {canonical_row_key(row) for row in current_rows if isinstance(row, dict)}
    out: list[Row] = []
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
    tokens: list[str] = []
    seen = set()
    for token in TOKEN_RE.findall(text.casefold()[:4000]):
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
        if len(tokens) >= max_tokens:
            break
    if not tokens:
        return None
    return " OR ".join(tokens)

def _build_conn(rows: list[Any]) -> Optional[sqlite3.Connection]:
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("CREATE VIRTUAL TABLE kb_fts USING fts5(text)")
        payload: list[tuple[int, str]] = []
        for index, row in enumerate(rows):
            text = _row_search_text(row)
            if not text:
                continue
            payload.append((index + 1, text))
        conn.executemany("INSERT INTO kb_fts(rowid, text) VALUES (?, ?)", payload)
        return conn
    except Exception:
        LOGGER.exception("Failed to build in-memory FTS index for %s row(s).", len(rows))
        try:
            if conn is not None:
                conn.close()
        except Exception:
            LOGGER.warning("Failed to close a partially initialized FTS index connection.", exc_info=True)
        return None

def get_or_build_index(
    session_id: Optional[str],
    kb_revision: int,
    rows: list[Any],
) -> Optional[sqlite3.Connection]:
    """Return a cached FTS index connection for the session.

    Args:
        session_id: Session id that owns the cache entry.
        kb_revision: Current knowledge-base revision number.
        rows: Rows to index when rebuilding.

    Returns:
        A reusable SQLite FTS connection, if indexing succeeds.
    """
    if not session_id:
        return None
    cached = INDEX_CACHE.get(session_id)
    # Cache entries are tied to kb_revision so an approval invalidates retrieval results
    # automatically without extra bookkeeping in the caller.
    if cached and cached[0] == kb_revision:
        return cached[1]
    if cached:
        try:
            cached[1].close()
        except Exception:
            LOGGER.warning("Failed to close stale FTS cache for session %s.", session_id, exc_info=True)
        INDEX_CACHE.pop(session_id, None)
    conn = _build_conn(rows)
    if conn is None:
        return None
    INDEX_CACHE[session_id] = (kb_revision, conn)
    return conn

def fts_candidate_indices(
    session_id: Optional[str],
    kb_revision: int,
    rows: list[Any],
    input_text: str,
    limit: int,
) -> list[int]:
    """Return likely matching row indices for a text query.

    Args:
        session_id: Session id tied to the cached index.
        kb_revision: Current knowledge-base revision number.
        rows: Candidate rows to index.
        input_text: User text to search against the rows.
        limit: Maximum number of row indices to return.

    Returns:
        Zero-based row indices ranked by FTS relevance.
    """
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
    except sqlite3.OperationalError as exc:
        LOGGER.warning("FTS query failed for session %s: %s", session_id or "<none>", exc)
        return []

def clear_index_cache() -> None:
    """Close and clear all cached FTS connections.

    Returns:
        None.
    """
    for _, conn in list(INDEX_CACHE.values()):
        try:
            conn.close()
        except Exception:
            LOGGER.warning("Failed to close an FTS cache connection during reset.", exc_info=True)
    INDEX_CACHE.clear()
