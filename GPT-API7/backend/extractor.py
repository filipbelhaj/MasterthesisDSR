import json
import math
import re
import time
import uuid
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from .config import ALLOW_DELETE, EMBEDDING_MODEL, EXTRACTOR_MODEL, FTS_CANDIDATES, TOPK, get_client
from .kb_index import fts_candidate_indices
from .prompt import SYSTEM_PROMPT
from .state import PROPOSALS, canonical_row_key, dedupe_rows, norm

STATEMENT_FIELDS = (
    "item",
    "itemLabel",
    "property",
    "propertyLabel",
    "value",
    "valueLabel",
    "qualifierProperty",
    "qualifierPropertyLabel",
    "qualifierValue",
    "qualifierValueLabel",
)
CHANGE_ACTIONS = ("create", "edit", "link", "delete", "uncertain")

REQUIRED_OUTPUT_SCHEMA = {
    "proposed_rows": [{
        "item": "string URI or provisional NEW:entity_x",
        "itemLabel": "string",
        "property": "property URI from ontology",
        "propertyLabel": "string",
        "value": "URI or literal",
        "valueLabel": "optional string",
        "qualifierProperty": "optional qualifier property URI/string",
        "qualifierPropertyLabel": "optional string",
        "qualifierValue": "optional URI or literal",
        "qualifierValueLabel": "optional string",
    }],
    "changes": [{
        "id": "chg_001",
        "action": "create|edit|link|delete|uncertain",
        "entity_scope": "statement|entity",
        "target_ref": "existing URI or NEW:* or row-ref",
        "proposed_row_index": 0,
        "justification": "why this was proposed",
        "evidence": [{"snippet": "source snippet", "start_char": 0, "end_char": 20}],
        "confidence": 0.0,
        "relevance_score": 0.0,
        "review_flag": "optional flag or null",
    }],
}

_INLINE_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_NEWLINE_PADDING_RE = re.compile(r"[ \t]*\n[ \t]*")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")

_ROW_EMBEDDING_CACHE: Dict[Tuple[Any, ...], List[float]] = {}

def _safe_int(value: Any) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return 0
    return out if out > 0 else 0

def _token_usage(response: Any) -> Dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")

    def _usage_field(name: str) -> Any:
        if usage is None:
            return None
        if isinstance(usage, dict):
            return usage.get(name)
        return getattr(usage, name, None)

    prompt_tokens = _safe_int(_usage_field("prompt_tokens"))
    completion_tokens = _safe_int(_usage_field("completion_tokens"))
    total_tokens = _safe_int(_usage_field("total_tokens"))

    if total_tokens == 0 and (prompt_tokens or completion_tokens):
        total_tokens = prompt_tokens + completion_tokens

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }

def empty_ontology_index() -> Dict[str, Any]:
    return {
        "raw": [],
        "by_entity": {},
        "items": [],
        "properties": [],
        "label_to_entities": {},
        "property_labels": {},
    }

def _compact_evidence(evidence_list: Any) -> List[str]:
    raw = [
        snippet.strip()
        for snippet in (
            e.get("snippet") if isinstance(e, dict) else None
            for e in (evidence_list or [])
        )
        if isinstance(snippet, str) and snippet.strip()
    ]

    def _norm_snippet(s: str) -> str:
        s = " ".join(s.lower().split())
        s = re.sub(r"[^a-z0-9 ]+", "", s)
        return s.strip()

    def _near_duplicate(a: str, b: str) -> bool:
        if not a or not b:
            return False
        if a == b:
            return True
        # Fast containment check catches many "same snippet with a few extra words".
        if a in b or b in a:
            shorter = min(len(a), len(b))
            longer = max(len(a), len(b))
            return (shorter / longer) >= 0.65
        # Fallback similarity for small lists.
        return SequenceMatcher(None, a, b).ratio() >= 0.92

    deduped: List[str] = []
    deduped_norm: List[str] = []
    for snippet in raw:
        ns = _norm_snippet(snippet)
        if not ns:
            continue

        replaced = False
        skip = False
        for i, existing_norm in enumerate(deduped_norm):
            if not _near_duplicate(existing_norm, ns):
                continue
            # Keep the more informative (usually longer) snippet.
            if len(snippet) > len(deduped[i]):
                deduped[i] = snippet
                deduped_norm[i] = ns
                replaced = True
            skip = True
            break
        if replaced:
            continue
        if skip:
            continue
        deduped.append(snippet)
        deduped_norm.append(ns)

    # Keep evidence short/scan-friendly.
    return deduped[:6]

def _statement_parts(row: Any) -> Tuple[str, Optional[str]]:
    if not isinstance(row, dict):
        return "Unknown item", None
    subject = row.get("itemLabel") or row.get("item") or "Unknown item"
    prop_label = row.get("propertyLabel") or row.get("property") or "unknown property"
    raw_value = row.get("valueLabel")
    if raw_value is None:
        raw_value = row.get("value")
    value_text = ("" if raw_value is None else str(raw_value)).replace("\n", " ").strip()
    if isinstance(raw_value, str) and len(value_text) > 260:
        value_text = value_text[:259].rstrip() + "…"
    statement = f"{prop_label} → {value_text}" if value_text else prop_label
    qprop = row.get("qualifierPropertyLabel") or row.get("qualifierProperty")
    qval = row.get("qualifierValueLabel") or row.get("qualifierValue")
    if qprop and qval:
        statement += f" [qualifier: {qprop} → {qval}]"
    return subject, statement

def _what_label(action: str, entity_scope: Any) -> str:
    if action == "create":
        return "Create entity" if entity_scope == "entity" else "Create statement"
    if action == "edit":
        return "Edit"
    if action == "link":
        return "Link to existing entity"
    if action == "delete":
        return "Delete"
    return "Needs review"

def _compact_entities(rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    return [{
        "entity": row.get("entity"),
        "entityLabel": row.get("entityLabel"),
        "entityDescription": row.get("entityDescription"),
    } for row in rows[:limit]]

def _existing_item_labels(base_rows: List[Dict[str, Any]]) -> List[str]:
    return sorted({
        row.get("itemLabel")
        for row in base_rows
        if isinstance(row, dict) and row.get("itemLabel")
    })[:500]

class OntologyStore:
    def __init__(self):
        self.rows: List[Dict[str, Any]] = []
        self.index: Dict[str, Any] = empty_ontology_index()
        self.compact_prompt_cache: Dict[str, Any] = {"properties": [], "items": []}
        self.load_error: Optional[str] = None

    def build_index(self, ontology_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_entity: Dict[str, Dict[str, Any]] = {}
        items: List[Dict[str, Any]] = []
        properties: List[Dict[str, Any]] = []
        label_to_entities: Dict[str, List[str]] = {}
        property_labels: Dict[str, str] = {}
        for row in ontology_rows:
            entity = row.get("entity")
            label = row.get("entityLabel")
            row_type = row.get("entityType")
            if entity:
                by_entity[entity] = row
            if label and entity:
                label_to_entities.setdefault(norm(label), []).append(entity)
            if row_type == "item":
                items.append(row)
            elif row_type == "property":
                properties.append(row)
                if label and entity:
                    property_labels[norm(label)] = entity
        return {
            "raw": ontology_rows,
            "by_entity": by_entity,
            "items": items,
            "properties": properties,
            "label_to_entities": label_to_entities,
            "property_labels": property_labels,
        }

    def load(self, ontology_rows: List[Dict[str, Any]]):
        self.rows = ontology_rows
        self.index = self.build_index(ontology_rows)
        self.compact_prompt_cache = {
            "properties": _compact_entities(self.index["properties"], 1000),
            "items": _compact_entities(self.index["items"], 800),
        }
        self.load_error = None

ONTOLOGY = OntologyStore()

def is_valid_property_uri(uri: Optional[str]) -> bool:
    if not uri:
        return False
    row = ONTOLOGY.index["by_entity"].get(uri)
    return bool(row and row.get("entityType") == "property")

def clean_statement_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if row.get("item") is None or row.get("property") is None or row.get("value") is None:
        return None
    if not is_valid_property_uri(row.get("property")):
        return None
    return {k: v for k, v in ((field, row.get(field)) for field in STATEMENT_FIELDS) if v is not None}

def compact_ontology_for_prompt() -> Dict[str, Any]:
    return ONTOLOGY.compact_prompt_cache

def normalize_input_text(input_text: str) -> str:
    text = (input_text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _NEWLINE_PADDING_RE.sub("\n", text)
    text = _INLINE_WHITESPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()

def _truncate_str(value: Any, limit: int) -> Any:
    if not isinstance(value, str):
        return value
    s = value.strip()
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)].rstrip() + "…"

def _row_text_for_embedding(row: Dict[str, Any]) -> str:
    parts = [
        row.get("itemLabel") or row.get("item"),
        row.get("propertyLabel") or row.get("property"),
        row.get("valueLabel"),
    ]
    if parts[-1] is None:
        parts[-1] = row.get("value")
    qprop = row.get("qualifierPropertyLabel") or row.get("qualifierProperty")
    qval = row.get("qualifierValueLabel")
    if qval is None:
        qval = row.get("qualifierValue")
    if qprop and qval:
        parts.append(f"{qprop}: {qval}")
    return " | ".join(str(p) for p in parts if p is not None).replace("\n", " ").strip()

def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na) * math.sqrt(nb)
    return (dot / denom) if denom else -1.0

def _embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    if not texts:
        return []
    try:
        resp = get_client().embeddings.create(model=EMBEDDING_MODEL, input=texts)
        data = getattr(resp, "data", None)
        if not data and isinstance(resp, dict):
            data = resp.get("data")
        if not isinstance(data, list):
            return None
        vectors: List[List[float]] = []
        for item in data:
            emb = item.get("embedding") if isinstance(item, dict) else getattr(item, "embedding", None)
            if not isinstance(emb, list):
                return None
            vectors.append([float(x) for x in emb])
        return vectors
    except Exception:
        return None

def _compact_row_for_prompt(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in STATEMENT_FIELDS:
        if k not in row:
            continue
        v = row.get(k)
        if v is None:
            continue
        # Avoid gigantic payloads (some qualifier values can be full paragraphs).
        out[k] = _truncate_str(v, 420)
    return out

def select_preview_rows(
    input_text: str,
    base_rows: List[Dict[str, Any]],
    topk: int,
    *,
    session_id: Optional[str] = None,
    kb_revision: int = 0,
) -> List[Dict[str, Any]]:
    """
    Choose a small set of base KB rows that are most relevant to the source text.
    This helps the model link to existing entities/statements instead of duplicating them.
    """
    if not base_rows or topk <= 0:
        return []

    haystack = norm(input_text)

    # 1) Cheap lexical hits first (fast + no API calls).
    lexical: List[Dict[str, Any]] = []
    seen_keys = set()
    for row in base_rows:
        if not isinstance(row, dict):
            continue
        item_label = row.get("itemLabel")
        value_label = row.get("valueLabel")
        if item_label and norm(str(item_label)) in haystack:
            k = canonical_row_key(row)
            if k not in seen_keys:
                seen_keys.add(k)
                lexical.append(row)
                if len(lexical) >= topk:
                    return [_compact_row_for_prompt(r) for r in lexical[:topk]]
        if value_label and norm(str(value_label)) in haystack:
            k = canonical_row_key(row)
            if k not in seen_keys:
                seen_keys.add(k)
                lexical.append(row)
                if len(lexical) >= topk:
                    return [_compact_row_for_prompt(r) for r in lexical[:topk]]

    # 2) Full-KB retrieval using SQLite FTS candidates (fast, bounded).
    # We still only embed/rerank a bounded subset to control latency/cost.
    fts_limit = int(FTS_CANDIDATES) if isinstance(FTS_CANDIDATES, int) else 450
    if fts_limit <= 0:
        fts_limit = 450
    idxs = fts_candidate_indices(
        session_id=session_id,
        kb_revision=kb_revision,
        rows=base_rows,
        input_text=input_text,
        limit=fts_limit,
    )
    candidates = [base_rows[i] for i in idxs if isinstance(i, int) and 0 <= i < len(base_rows) and isinstance(base_rows[i], dict)]
    if not candidates:
        # Fallback: keep behavior reasonable even if FTS isn't available.
        max_candidates = 1200
        candidates = [r for r in base_rows[:max_candidates] if isinstance(r, dict)]
        if not candidates:
            return [_compact_row_for_prompt(r) for r in lexical[:topk]]

    query_vecs = _embed_texts([_truncate_str(normalize_input_text(input_text), 1600)])
    if not query_vecs:
        combined = lexical + [r for r in candidates if canonical_row_key(r) not in seen_keys]
        return [_compact_row_for_prompt(r) for r in combined[:topk]]
    query_vec = query_vecs[0]

    texts: List[str] = []
    missing_keys: List[Tuple[Any, ...]] = []
    for row in candidates:
        k = canonical_row_key(row)
        if k in _ROW_EMBEDDING_CACHE:
            continue
        missing_keys.append(k)
        texts.append(_truncate_str(_row_text_for_embedding(row), 900))

    # Batch embed (OpenAI embeddings API accepts list inputs).
    if texts:
        vectors = _embed_texts(texts)
        if vectors and len(vectors) == len(missing_keys):
            for k, v in zip(missing_keys, vectors):
                _ROW_EMBEDDING_CACHE[k] = v

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for row in candidates:
        k = canonical_row_key(row)
        vec = _ROW_EMBEDDING_CACHE.get(k)
        if not vec:
            continue
        scored.append((_cosine_similarity(query_vec, vec), row))

    scored.sort(key=lambda t: t[0], reverse=True)
    selected: List[Dict[str, Any]] = list(lexical)
    for _, row in scored:
        k = canonical_row_key(row)
        if k in seen_keys:
            continue
        seen_keys.add(k)
        selected.append(row)
        if len(selected) >= topk:
            break

    return [_compact_row_for_prompt(r) for r in selected[:topk]]

def build_prompt_payload(
    input_text: str,
    base_rows: List[Dict[str, Any]],
    *,
    session_id: Optional[str] = None,
    kb_revision: int = 0,
) -> Dict[str, Any]:
    preview_rows = select_preview_rows(input_text, base_rows, TOPK, session_id=session_id, kb_revision=kb_revision)
    return {
        "task": "Extract ontology-valid Wikibase-like rows and a reasoning/change report",
        "source_text": normalize_input_text(input_text),
        "ontology": compact_ontology_for_prompt(),
        "existing_kb_preview_rows": preview_rows,
        "existing_kb_preview_note": "Rows are retrieved from the existing KB for relevance to the source text; do not assume they are exhaustive.",
        "existing_kb_item_labels_sample": _existing_item_labels(base_rows),
        "required_output_schema": REQUIRED_OUTPUT_SCHEMA,
    }

def call_extractor(
    input_text: str,
    base_rows: List[Dict[str, Any]],
    *,
    session_id: Optional[str] = None,
    kb_revision: int = 0,
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    if ONTOLOGY.load_error:
        raise RuntimeError(f"Failed to load ontology: {ONTOLOGY.load_error}")
    payload = build_prompt_payload(input_text, base_rows, session_id=session_id, kb_revision=kb_revision)
    response = get_client().chat.completions.create(
        model=EXTRACTOR_MODEL,
        temperature=0.1, #Ändra till lägre om mer precision önskas, högre för mer kreativa förslag (Funkar bara med 5.4)
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )
    content = response.choices[0].message.content or "{}"
    try:
        return json.loads(content), _token_usage(response)
    except Exception as exc:
        raise RuntimeError(f"Extractor returned invalid JSON: {exc}\\nRaw: {content[:1000]}")

def validate_llm_output(llm_out: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    raw_rows = llm_out.get("proposed_rows", [])
    raw_changes = llm_out.get("changes", [])
    warnings: List[str] = []
    if not isinstance(raw_rows, list):
        raw_rows = []
        warnings.append("LLM output `proposed_rows` was not a list.")
    if not isinstance(raw_changes, list):
        raw_changes = []
        warnings.append("LLM output `changes` was not a list.")

    valid_rows: List[Dict[str, Any]] = []
    for idx, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            warnings.append(f"proposed_rows[{idx}] ignored (not an object)")
            continue
        cleaned = clean_statement_row(row)
        if not cleaned:
            warnings.append(f"proposed_rows[{idx}] ignored (missing fields or invalid property)")
            continue
        valid_rows.append(cleaned)
    return dedupe_rows(valid_rows), raw_changes, warnings

def merge_proposal_into_base(base_rows, proposal_rows, changes):
    base_copy = deepcopy(base_rows)
    base_keys = {canonical_row_key(row) for row in base_copy if isinstance(row, dict)}
    delete_keys = set()
    if ALLOW_DELETE:
        for change in changes:
            if not isinstance(change, dict) or change.get("action") != "delete":
                continue
            idx = change.get("proposed_row_index")
            if isinstance(idx, int) and 0 <= idx < len(proposal_rows):
                delete_keys.add(canonical_row_key(proposal_rows[idx]))

    kept_rows = [row for row in base_copy if canonical_row_key(row) not in delete_keys]
    added_rows = []
    for row in proposal_rows:
        row_key = canonical_row_key(row)
        if row_key not in base_keys:
            kept_rows.append(row)
            added_rows.append(row)
    return {
        "merged_rows": dedupe_rows(kept_rows),
        "diff": {"added_rows": added_rows, "edited_rows": [], "deleted_rows": []},
    }

def normalize_reasoning_report(raw_changes, proposal_rows, validation_warnings):
    counts = {action: 0 for action in CHANGE_ACTIONS}
    changes_out = []
    for change in raw_changes:
        if not isinstance(change, dict):
            continue
        action = change.get("action", "uncertain")
        if action not in counts:
            action = "uncertain"
        counts[action] += 1

        idx = change.get("proposed_row_index")
        proposed_row = proposal_rows[idx] if isinstance(idx, int) and 0 <= idx < len(proposal_rows) else None
        evidence = change.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = []
        subject, statement_preview = _statement_parts(proposed_row)
        changes_out.append({
            "what": _what_label(action, change.get("entity_scope", "statement")),
            "subject": subject,
            "statement": statement_preview,
            "why": ("" if change.get("justification", "") is None else str(change.get("justification", ""))).strip(),
            "evidence": _compact_evidence(evidence),
            "confidence": change.get("confidence", 0.0),
            "relevance": change.get("relevance_score", None),
            "needs_review": change.get("review_flag"),
        })
    return {
        "summary": {
            "creates": counts["create"],
            "edits": counts["edit"],
            "links": counts["link"],
            "deletes": counts["delete"],
            "uncertain": counts["uncertain"],
            "validation_warnings": len(validation_warnings),
        },
        "validation_warnings": validation_warnings,
        "proposed_changes": changes_out,
    }

def generate_proposal(
    input_text: str,
    base_rows: List[Dict[str, Any]],
    *,
    session_id: Optional[str] = None,
    kb_revision: int = 0,
) -> Dict[str, Any]:
    started = time.perf_counter()
    llm_out, token_usage = call_extractor(
        input_text=input_text,
        base_rows=base_rows,
        session_id=session_id,
        kb_revision=kb_revision,
    )
    proposal_rows, raw_changes, warnings = validate_llm_output(llm_out)
    merged = merge_proposal_into_base(base_rows, proposal_rows, raw_changes)
    reasoning = normalize_reasoning_report(raw_changes, proposal_rows, warnings)
    proposal_id = f"prop_{uuid.uuid4().hex[:10]}"
    generation_seconds = round(time.perf_counter() - started, 3)
    proposal = {
        "proposal_id": proposal_id,
        "patch_kb_json": merged["diff"]["added_rows"],
        "proposed_kb_json": merged["merged_rows"],
        "reasoning_report": reasoning,
        "diff": merged["diff"],
        "proposal_rows_only": proposal_rows,
        "generation_seconds": generation_seconds,
        "generation_tokens": token_usage.get("total_tokens", 0),
        "token_usage": token_usage,
        "created_at": time.time(),
    }
    PROPOSALS[proposal_id] = proposal
    return proposal
