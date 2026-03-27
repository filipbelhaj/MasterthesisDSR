import json
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from .core.config import (
    ALLOW_DELETE,
    DEFAULT_QUERY_FILE,
    EMBEDDING_MODEL,
    ENTITY_CATALOG_LIMIT,
    ENTITY_NEIGHBORHOOD_PER_ENTITY,
    ENTITY_NEIGHBORHOOD_SHARE,
    EXTRACTOR_MODEL,
    EXTRACTOR_TEMPERATURE,
    FTS_CANDIDATES,
    FTS_QUERY_MAX_TOKENS,
    ONTOLOGY_FILE,
    TOPK,
)
from .extractor.context import clear_row_embedding_cache, resolve_existing_entities
from .extractor.ontology import ONTOLOGY
from .extractor.pipeline import generate_proposal
from .state import (
    PROPOSALS,
    SESSIONS,
    canonical_row_key,
    clear_index_cache,
    dedupe_rows,
    get_or_create_session,
    load_json_file,
    rows_delta,
    rows_removed,
)
from .quickstatements import (
    build_step2_quickstatements,
    placeholder_create_quickstatements,
    placeholder_manifest_template,
    rows_to_quickstatements,
    sanitize_rows_for_quickstatements,
)

SessionMode = Literal["create_new", "extend_existing"]

class ProposeRequest(BaseModel):
    input_text: str
    session_id: Optional[str] = None
    mode: Optional[SessionMode] = None


class ApproveRequest(BaseModel):
    session_id: str
    proposal_id: str
    edited_kb_json: Optional[List[Dict[str, Any]]] = None


class QuickStatementsBinding(BaseModel):
    placeholder: str
    qid: Optional[str] = None


class QuickStatementsStep2Request(BaseModel):
    bindings: List[QuickStatementsBinding]

api_router = APIRouter(prefix="/api", tags=["api"])
health_router = APIRouter(tags=["health"])

def as_row_list(rows: Any) -> list[dict[str, Any]]:
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

def current_rows(session: dict[str, Any]) -> list[dict[str, Any]]:
    return as_row_list(session.get("current_kb_json", []))

def require_input_text(input_text: str) -> None:
    if not input_text or not input_text.strip():
        raise HTTPException(status_code=400, detail="input_text is required")

def require_value(mapping: dict[str, Any], key: str, detail: str) -> Any:
    value = mapping.get(key)
    if value is None:
        raise HTTPException(status_code=404, detail=detail)
    return value

def session_or_none(session_id: str) -> Tuple[Optional[str], Optional[dict[str, Any]]]:
    sid = (session_id or "").strip()
    if not sid:
        return None, None
    return sid, SESSIONS.get(sid)

def non_negative_int(value: Any, default: int = 0) -> int:
    return value if isinstance(value, int) and value >= 0 else default

def line_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())


def unique_texts(values: List[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def quickstatements_empty(session_id: str) -> dict[str, Any]:
    return {"exists": False, "session_id": session_id, "quickstatements": "", "line_count": 0}

def get_base_rows_for_session(session: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    session = session if isinstance(session, dict) else None
    base_rows = session.get("base_kb_json") if session else None
    if isinstance(base_rows, list) and base_rows:
        return as_row_list(base_rows)

    try:
        loaded = load_json_file(DEFAULT_QUERY_FILE) if DEFAULT_QUERY_FILE.exists() else []
    except Exception:
        loaded = []
    loaded = as_row_list(loaded)

    if session is not None:
        session["base_kb_json"] = loaded
    return loaded

def session_rows(
    session: dict[str, Any],
) -> Tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    base_rows = get_base_rows_for_session(session)
    current = current_rows(session)
    return base_rows, current, rows_delta(base_rows, current), rows_removed(base_rows, current)

def proposal_removed_rows(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    diff = proposal.get("diff") if isinstance(proposal, dict) else None
    if not isinstance(diff, dict):
        return []

    removed = as_row_list(diff.get("deleted_rows", []))
    edited_rows = diff.get("edited_rows", [])
    if isinstance(edited_rows, list):
        for entry in edited_rows:
            if not isinstance(entry, dict):
                continue
            before = entry.get("before")
            if isinstance(before, dict):
                removed.append(before)
    return dedupe_rows(removed)

def safe_generate_proposal(
    input_text: str,
    base_rows: list[dict[str, Any]],
    session_id: str,
    kb_revision: int,
) -> dict[str, Any]:
    try:
        return generate_proposal(input_text, base_rows, session_id=session_id, kb_revision=kb_revision)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

def reset_server_state_on_kb_change() -> None:
    SESSIONS.clear()
    PROPOSALS.clear()
    clear_index_cache()
    clear_row_embedding_cache()

async def upload_json_array(
    file: UploadFile,
    out_name: str,
    array_error: str,
    success_message: str,
    on_success=None,
) -> dict[str, Any]:
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

def health_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "ontology_file": str(ONTOLOGY_FILE),
        "ontology_rows": len(ONTOLOGY.rows),
        "ontology_load_error": ONTOLOGY.load_error,
        "default_query_file_exists": DEFAULT_QUERY_FILE.exists(),
        "sessions": len(SESSIONS),
        "proposals": len(PROPOSALS),
        "extractor_model": EXTRACTOR_MODEL,
        "extractor_temperature": EXTRACTOR_TEMPERATURE,
        "embedding_model": EMBEDDING_MODEL,
        "topk": TOPK,
        "fts_candidates": FTS_CANDIDATES,
        "fts_query_max_tokens": FTS_QUERY_MAX_TOKENS,
        "entity_catalog_limit": ENTITY_CATALOG_LIMIT,
        "entity_neighborhood_share": ENTITY_NEIGHBORHOOD_SHARE,
        "entity_neighborhood_per_entity": ENTITY_NEIGHBORHOOD_PER_ENTITY,
        "allow_delete": ALLOW_DELETE,
    }

@api_router.get("/health")
def api_health():
    return health_payload()

@health_router.get("/health")
def root_health():
    return health_payload()

@api_router.get("/state/{session_id}")
def api_state(session_id: str):
    sid, session = session_or_none(session_id)
    if session is None:
        base_rows = get_base_rows_for_session()
        return {
            "exists": False,
            "session_id": sid or session_id,
            "base_kb_json": base_rows,
            "current_kb_json": [],
            "delta_kb_json": [],
            "removed_kb_json": [],
            "change_kb_json": {"added_rows": [], "deleted_rows": []},
            "history_count": 0,
            "token_usage_total": 0,
            "created_at": None,
        }

    base_rows, current_kb_rows, delta_rows, removed_rows = session_rows(session)
    token_usage_total = non_negative_int(session.get("token_usage_total", 0))
    session["token_usage_total"] = token_usage_total
    return {
        "exists": True,
        "session_id": session_id,
        "mode": session.get("mode"),
        "base_kb_json": base_rows,
        "current_kb_json": current_kb_rows,
        "delta_kb_json": delta_rows,
        "removed_kb_json": removed_rows,
        "change_kb_json": {
            "added_rows": delta_rows,
            "deleted_rows": removed_rows,
        },
        "history_count": len(session["history"]),
        "token_usage_total": token_usage_total,
        "created_at": session["created_at"],
    }

@api_router.get("/default-query")
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

@api_router.get("/quickstatements/{session_id}")
def api_quickstatements(session_id: str, lang: str = "en"):
    sid, session = session_or_none(session_id)
    if session is None:
        return quickstatements_empty(sid or session_id)

    base_rows, _, delta_rows, removed_rows = session_rows(session)
    delta_rows = resolve_existing_entities(delta_rows, base_rows, warnings=None)
    manifest_template, manifest_warnings = placeholder_manifest_template(delta_rows)
    delete_warnings = []
    if removed_rows:
        delete_warnings.append(
            "Deleted rows are not included in QuickStatements output. Review the final JSON export for `deleted_rows`."
        )
    if manifest_template:
        step1_qs, manifest_entries, step1_warnings = placeholder_create_quickstatements(delta_rows, lang=lang)
        return {
            "exists": True,
            "session_id": session_id,
            "mode": "two_step",
            "quickstatements": step1_qs,
            "line_count": line_count(step1_qs),
            "warnings": unique_texts(manifest_warnings + step1_warnings + delete_warnings),
            "skipped_rows": 0,
            "removed_rows": removed_rows,
            "step1_quickstatements": step1_qs,
            "step1_placeholders": manifest_entries,
            "step2_quickstatements": "",
            "step2_warnings": [],
            "step2_unresolved_placeholders": manifest_template,
            "binding_template": manifest_template,
        }

    qs_rows, qs_warnings, row_index_map = sanitize_rows_for_quickstatements(delta_rows)
    qs_text = rows_to_quickstatements(qs_rows, lang=lang)
    skipped_rows = sum(1 for mapped in row_index_map.values() if mapped is None)
    return {
        "exists": True,
        "session_id": session_id,
        "mode": "single_step",
        "quickstatements": qs_text,
        "line_count": line_count(qs_text),
        "warnings": unique_texts(qs_warnings + delete_warnings),
        "skipped_rows": skipped_rows,
        "removed_rows": removed_rows,
        "step1_quickstatements": "",
        "step1_placeholders": [],
        "step2_quickstatements": qs_text,
        "step2_warnings": unique_texts(qs_warnings + delete_warnings),
        "step2_unresolved_placeholders": [],
        "binding_template": [],
    }

@api_router.post("/quickstatements/{session_id}/step2")
def api_quickstatements_step2(session_id: str, req: QuickStatementsStep2Request, lang: str = "en"):
    sid, session = session_or_none(session_id)
    if session is None:
        return quickstatements_empty(sid or session_id)

    base_rows, _, delta_rows, removed_rows = session_rows(session)
    delta_rows = resolve_existing_entities(delta_rows, base_rows, warnings=None)
    bindings = {
        binding.placeholder: binding.qid or ""
        for binding in req.bindings
        if isinstance(binding.placeholder, str) and binding.placeholder.strip()
    }
    result = build_step2_quickstatements(delta_rows, bindings, lang=lang)
    warnings = unique_texts(list(result["warnings"]))
    if removed_rows:
        warnings.append(
            "Deleted rows are not included in QuickStatements output. Review the final JSON export for `deleted_rows`."
        )
    warnings = unique_texts(warnings)
    return {
        "exists": True,
        "session_id": session_id,
        "quickstatements": result["quickstatements"],
        "line_count": line_count(result["quickstatements"]),
        "warnings": warnings,
        "skipped_rows": result["skipped_rows"],
        "unresolved_placeholders": result["unresolved_placeholders"],
        "removed_rows": removed_rows,
    }

@api_router.post("/upload-ontology")
async def api_upload_ontology(file: UploadFile = File(...)):
    return await upload_json_array(
        file=file,
        out_name=str(ONTOLOGY_FILE),
        array_error="Ontology must be a JSON array.",
        success_message="Ontology uploaded.",
        on_success=lambda data: (ONTOLOGY.load(data), reset_server_state_on_kb_change()),
    )

@api_router.post("/upload-query")
async def api_upload_query(file: UploadFile = File(...)):
    return await upload_json_array(
        file=file,
        out_name=str(DEFAULT_QUERY_FILE),
        array_error="query.json must be a JSON array.",
        success_message="Query uploaded.",
        on_success=lambda _data: reset_server_state_on_kb_change(),
    )

@api_router.post("/propose")
def api_propose(req: ProposeRequest):
    require_input_text(req.input_text)
    if ONTOLOGY.load_error:
        raise HTTPException(status_code=500, detail=f"Ontology load failed: {ONTOLOGY.load_error}")

    sid, session = get_or_create_session(req.session_id, mode=req.mode)
    base_rows = current_rows(session)
    kb_revision = non_negative_int(session.get("kb_revision", 0))
    session["kb_revision"] = kb_revision

    proposal = safe_generate_proposal(req.input_text, base_rows, session_id=sid, kb_revision=kb_revision)
    generation_tokens = non_negative_int(proposal.get("generation_tokens", 0))
    token_usage_total = non_negative_int(session.get("token_usage_total", 0))
    session["token_usage_total"] = token_usage_total + generation_tokens

    proposal["session_id"] = sid
    proposal["mode"] = session.get("mode")
    proposal["base_kb_json"] = base_rows
    proposal["session_tokens_total"] = session["token_usage_total"]
    return proposal

@api_router.post("/approve")
def api_approve(req: ApproveRequest):
    session = require_value(SESSIONS, req.session_id, "Unknown session_id")
    proposal = require_value(PROPOSALS, req.proposal_id, "Unknown proposal_id")
    proposal_session_id = proposal.get("session_id")
    if proposal_session_id and proposal_session_id != req.session_id:
        raise HTTPException(status_code=400, detail="proposal_id does not belong to the provided session_id")
    session_revision = non_negative_int(session.get("kb_revision", 0))
    proposal_revision = non_negative_int(proposal.get("kb_revision"), default=-1)
    if proposal_revision >= 0 and proposal_revision != session_revision:
        raise HTTPException(
            status_code=409,
            detail="Proposal is stale because the session changed after it was generated. Generate a new proposal.",
        )

    approved_kb_json = (
        req.edited_kb_json
        if req.edited_kb_json is not None
        else proposal.get("patch_kb_json", proposal["proposed_kb_json"])
    )
    if not isinstance(approved_kb_json, list):
        raise HTTPException(status_code=400, detail="edited_kb_json must be a JSON array")

    approved_patch_rows = as_row_list(approved_kb_json)
    existing_rows = current_rows(session)
    removed_keys = {canonical_row_key(row) for row in proposal_removed_rows(proposal)}
    kept_rows = [row for row in existing_rows if canonical_row_key(row) not in removed_keys]
    session["current_kb_json"] = dedupe_rows(kept_rows + approved_patch_rows)
    session["kb_revision"] = non_negative_int(session.get("kb_revision", 0)) + 1

    session["history"].append({
        "proposal_id": req.proposal_id,
        "approved_at": time.time(),
        "diff": proposal["diff"],
        "reasoning_report": proposal["reasoning_report"],
    })

    return {
        "ok": True,
        "message": "Proposal approved and applied to session state (deduplicated).",
        "current_kb_json": session["current_kb_json"],
        "history_count": len(session["history"]),
    }