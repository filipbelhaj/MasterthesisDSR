"""Shared response builders for API payloads returned by route handlers."""

from typing import Any, Optional

def line_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())

def build_state_payload(
    session_id: str,
    *,
    exists: bool,
    base_rows: list[dict[str, Any]],
    current_rows: Optional[list[dict[str, Any]]] = None,
    delta_rows: Optional[list[dict[str, Any]]] = None,
    removed_rows: Optional[list[dict[str, Any]]] = None,
    history_count: int = 0,
    token_usage_total: int = 0,
    created_at: Any = None,
    warnings: Optional[list[str]] = None,
    mode: Optional[str] = None,
    detail: Optional[str] = None,
) -> dict[str, Any]:
    added_rows = delta_rows or []
    deleted_rows = removed_rows or []
    payload = {
        "exists": exists,
        "session_id": session_id,
        "base_kb_json": base_rows,
        "current_kb_json": current_rows or [],
        "delta_kb_json": added_rows,
        "removed_kb_json": deleted_rows,
        "change_kb_json": {
            "added_rows": added_rows,
            "deleted_rows": deleted_rows,
        },
        "history_count": history_count,
        "token_usage_total": token_usage_total,
        "created_at": created_at,
        "warnings": warnings or [],
    }
    if mode is not None:
        payload["mode"] = mode
    if detail is not None:
        payload["detail"] = detail
    return payload

def build_quickstatements_payload(
    session_id: str,
    *,
    exists: bool = True,
    quickstatements: str = "",
    warnings: Optional[list[str]] = None,
    removed_rows: Optional[list[dict[str, Any]]] = None,
    lang: Optional[str] = None,
    detail: Optional[str] = None,
    **extra: Any,
) -> dict[str, Any]:
    payload = {
        "exists": exists,
        "session_id": session_id,
        "quickstatements": quickstatements,
        "line_count": line_count(quickstatements),
        "warnings": warnings or [],
        "removed_rows": removed_rows or [],
    }
    if lang is not None:
        payload["lang"] = lang
    if detail is not None:
        payload["detail"] = detail
    payload.update(extra)
    return payload
