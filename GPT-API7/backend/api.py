import json
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from .config import (ALLOW_DELETE, DEFAULT_QUERY_FILE, EMBEDDING_MODEL, EXTRACTOR_MODEL, ONTOLOGY_FILE, TOPK)
from .converter import rows_to_quickstatements
from .models import ApproveRequest, ProposeRequest
from .extractor import ONTOLOGY, generate_proposal
from .state import PROPOSALS, SESSIONS, dedupe_rows, get_or_create_session, load_json_file, rows_delta

router = APIRouter(prefix="/api", tags=["api"])

def _as_row_list(rows):
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

def _current_rows(session):
    return _as_row_list(session.get("current_kb_json", []))

def _require_input_text(input_text: str):
    if not input_text or not input_text.strip():
        raise HTTPException(status_code=400, detail="input_text is required")

def _require(mapping, key, detail):
    value = mapping.get(key)
    if value is None:
        raise HTTPException(status_code=404, detail=detail)
    return value

def _session_or_none(session_id: str):
    sid = (session_id or "").strip()
    if not sid:
        return None, None
    return sid, SESSIONS.get(sid)

def _safe_generate_proposal(input_text: str, base_rows, session_id: str, kb_revision: int):
    try:
        return generate_proposal(input_text, base_rows, session_id=session_id, kb_revision=kb_revision)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

async def _upload_json_array(file: UploadFile, out_name: str, array_error: str, success_message: str, on_success=None):
    raw = await file.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON file.")

    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail=array_error)

    Path(out_name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if on_success is not None:
        on_success(data)

    return {
        "ok": True,
        "message": success_message,
        "saved_as": out_name,
        "original_filename": file.filename,
        "rows": len(data),
    }

def _get_base_rows_for_session(session):
    base_rows = session.get("base_kb_json")

    # If a session already has (non-empty) base rows, just use them.
    if isinstance(base_rows, list) and base_rows:
        return _as_row_list(base_rows)

    # Otherwise, try loading from the default query file (if present).
    try:
        loaded = load_json_file(DEFAULT_QUERY_FILE) if DEFAULT_QUERY_FILE.exists() else []
    except Exception:
        loaded = []
    loaded = _as_row_list(loaded)

    # Keep for future requests in this session.
    session["base_kb_json"] = loaded
    return loaded

@router.get("/health")
def api_health():
    return {
        "ok": True,
        "ontology_file": str(ONTOLOGY_FILE),
        "ontology_rows": len(ONTOLOGY.rows),
        "ontology_load_error": ONTOLOGY.load_error,
        "default_query_file_exists": DEFAULT_QUERY_FILE.exists(),
        "sessions": len(SESSIONS),
        "proposals": len(PROPOSALS),
        "extractor_model": EXTRACTOR_MODEL,
        "embedding_model": EMBEDDING_MODEL,
        "topk": TOPK,
        "allow_delete": ALLOW_DELETE,
    }

@router.get("/state/{session_id}")
def api_state(session_id: str):
    sid, session = _session_or_none(session_id)
    if session is None:
        # Avoid noisy 404s in the browser console when a user has a stale session id in localStorage
        # (sessions are in-memory only and disappear on server restart).
        base_rows = _get_base_rows_for_session({})
        return {
            "exists": False,
            "session_id": sid or session_id,
            "base_kb_json": base_rows,
            "current_kb_json": [],
            "delta_kb_json": [],
            "history_count": 0,
            "token_usage_total": 0,
            "created_at": None,
        }
    base_rows = _get_base_rows_for_session(session)
    current_rows = _current_rows(session)
    delta_rows = rows_delta(base_rows, current_rows)
    token_usage_total = session.get("token_usage_total", 0)
    if not isinstance(token_usage_total, int) or token_usage_total < 0:
        token_usage_total = 0
    session["token_usage_total"] = token_usage_total

    return {
        "exists": True,
        "session_id": session_id,
        "mode": session.get("mode"),
        "base_kb_json": base_rows,
        "current_kb_json": current_rows,
        "delta_kb_json": delta_rows,
        "history_count": len(session["history"]),
        "token_usage_total": token_usage_total,
        "created_at": session["created_at"],
    }

@router.get("/quickstatements/{session_id}")
def api_quickstatements(session_id: str, lang: str = "en"):
    sid, session = _session_or_none(session_id)
    if session is None:
        return {"exists": False, "session_id": sid or session_id, "quickstatements": "", "line_count": 0}
    base_rows = _get_base_rows_for_session(session)
    current_rows = _current_rows(session)
    delta_rows = rows_delta(base_rows, current_rows)

    qs_text = rows_to_quickstatements(delta_rows, lang=lang)
    line_count = sum(1 for ln in qs_text.splitlines() if ln.strip())
    return {"exists": True, "session_id": session_id, "quickstatements": qs_text, "line_count": line_count}

@router.post("/upload-ontology")
async def api_upload_ontology(file: UploadFile = File(...)):
    return await _upload_json_array(
        file=file,
        out_name="ontology.json",
        array_error="Ontology must be a JSON array.",
        success_message="Ontology uploaded.",
        on_success=ONTOLOGY.load,
    )

@router.post("/upload-query")
async def api_upload_query(file: UploadFile = File(...)):
    return await _upload_json_array(
        file=file,
        out_name="query.json",
        array_error="query.json must be a JSON array.",
        success_message="Query uploaded.",
    )

@router.post("/propose")
def api_propose(req: ProposeRequest):
    _require_input_text(req.input_text)
    if ONTOLOGY.load_error:
        raise HTTPException(status_code=500, detail=f"Ontology load failed: {ONTOLOGY.load_error}")

    sid, session = get_or_create_session(req.session_id, mode=req.mode)

    base_rows = _current_rows(session)

    kb_revision = session.get("kb_revision", 0)
    if not isinstance(kb_revision, int) or kb_revision < 0:
        kb_revision = 0
        session["kb_revision"] = 0

    proposal = _safe_generate_proposal(req.input_text, base_rows, session_id=sid, kb_revision=kb_revision)
    generation_tokens = proposal.get("generation_tokens", 0)
    if not isinstance(generation_tokens, int) or generation_tokens < 0:
        generation_tokens = 0

    token_usage_total = session.get("token_usage_total", 0)
    if not isinstance(token_usage_total, int) or token_usage_total < 0:
        token_usage_total = 0

    session["token_usage_total"] = token_usage_total + generation_tokens

    proposal["session_id"] = sid
    proposal["mode"] = session.get("mode")
    proposal["base_kb_json"] = base_rows
    proposal["session_tokens_total"] = session["token_usage_total"]
    return proposal

@router.post("/approve")
def api_approve(req: ApproveRequest):
    session = _require(SESSIONS, req.session_id, "Unknown session_id")
    proposal = _require(PROPOSALS, req.proposal_id, "Unknown proposal_id")

    approved_kb_json = req.edited_kb_json if req.edited_kb_json is not None else proposal.get("patch_kb_json", proposal["proposed_kb_json"])
    if not isinstance(approved_kb_json, list):
        raise HTTPException(status_code=400, detail="edited_kb_json must be a JSON array")

    existing_rows = _current_rows(session)
    merged_input = existing_rows + _as_row_list(approved_kb_json)
    session["current_kb_json"] = dedupe_rows(merged_input)
    session["kb_revision"] = (session.get("kb_revision", 0) or 0) + 1

    session["history"].append({
        "proposal_id": req.proposal_id,
        "approved_at": time.time(),
        "diff": proposal["diff"],
        "reasoning_report": proposal["reasoning_report"],
    })

    return {
        "ok": True,
        "message": "Proposal approved and appended to session state (deduplicated).",
        "current_kb_json": session["current_kb_json"],
        "history_count": len(session["history"]),
    }

@router.get("/default-query")
def api_default_query():
    if not DEFAULT_QUERY_FILE.exists():
        return {"exists": False, "rows": []}
    try:
        rows = load_json_file(DEFAULT_QUERY_FILE)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read query file: {exc}")
    if not isinstance(rows, list):
        raise HTTPException(status_code=500, detail="query.json must be a JSON array")
    return {"exists": True, "rows": rows}
