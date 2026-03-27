import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
from ..core.config import (
    ENTITY_CATALOG_LIMIT,
    EXTRACTOR_MODEL,
    EXTRACTOR_TEMPERATURE,
    TOPK,
    get_client,
)
from ..state import PROPOSALS, dedupe_rows
from ..core.prompt import SYSTEM_PROMPT
from .context import (
    entity_ids_from_catalog,
    existing_entity_catalog_for_input,
    existing_item_labels,
    normalize_input_text,
    resolve_existing_entities,
    select_preview_rows,
    structured_reference_style_examples,
)
from .ontology import ONTOLOGY, compact_ontology_for_prompt
from .postprocess import merge_proposal_into_base, normalize_reasoning_report, validate_llm_output

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

ENTITY_CATALOG_NOTE = (
    "Label->entity mappings for labels or structured-reference aliases found in the source text "
    "(unique labels only). Prefer these ids over NEW:*; canonical_label shows the KB label "
    "when the matched source alias differs."
)
STRUCTURED_REFERENCE_NOTE = (
    "Existing structured-reference nodes often act as anchors. Prefer direct properties "
    "consistent with these examples; otherwise attach the semantics to a connected rule/"
    "concept entity instead of the reference node itself."
)
def token_usage(response: Any) -> Dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")

    def usage_field(name: str) -> Any:
        if usage is None:
            return None
        if isinstance(usage, dict):
            return usage.get(name)
        return getattr(usage, name, None)

    def positive_int(name: str) -> int:
        try:
            value = int(usage_field(name))
        except (TypeError, ValueError):
            return 0
        return value if value > 0 else 0

    prompt_tokens = positive_int("prompt_tokens")
    completion_tokens = positive_int("completion_tokens")
    total_tokens = positive_int("total_tokens")
    if total_tokens == 0 and (prompt_tokens or completion_tokens):
        total_tokens = prompt_tokens + completion_tokens

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }

def _build_kb_prompt_context(
    input_text: str,
    base_rows: List[Dict[str, Any]],
    *,
    session_id: Optional[str] = None,
    kb_revision: int = 0,
) -> Dict[str, Any]:
    entity_catalog = existing_entity_catalog_for_input(input_text, base_rows, limit=ENTITY_CATALOG_LIMIT)
    matched_entity_ids = entity_ids_from_catalog(entity_catalog)
    return {
        "existing_kb_preview_rows": select_preview_rows(
            input_text,
            base_rows,
            TOPK,
            session_id=session_id,
            kb_revision=kb_revision,
            matched_entity_ids=matched_entity_ids,
        ),
        "existing_kb_preview_note": "Rows are retrieved from the existing KB for relevance to the source text; do not assume they are exhaustive.",
        "existing_kb_entity_catalog": entity_catalog,
        "existing_kb_entity_catalog_note": ENTITY_CATALOG_NOTE,
        "existing_kb_structured_reference_examples": structured_reference_style_examples(entity_catalog, base_rows),
        "existing_kb_structured_reference_examples_note": STRUCTURED_REFERENCE_NOTE,
        "existing_kb_item_labels_sample": existing_item_labels(input_text, base_rows),
    }

def _edited_after_rows(merged: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        entry["after"]
        for entry in merged["diff"]["edited_rows"]
        if isinstance(entry, dict) and isinstance(entry.get("after"), dict)
    ]

def _build_proposal_record(
    merged: Dict[str, Any],
    proposal_rows: List[Dict[str, Any]],
    reasoning: Dict[str, Any],
    usage: Dict[str, int],
    generation_seconds: float,
    session_id: Optional[str] = None,
    kb_revision: int = 0,
) -> Dict[str, Any]:
    return {
        "proposal_id": f"prop_{uuid.uuid4().hex[:10]}",
        "session_id": session_id,
        "kb_revision": kb_revision,
        "patch_kb_json": dedupe_rows(merged["diff"]["added_rows"] + _edited_after_rows(merged)),
        "proposed_kb_json": merged["merged_rows"],
        "reasoning_report": reasoning,
        "diff": merged["diff"],
        "proposal_rows_only": proposal_rows,
        "generation_seconds": generation_seconds,
        "generation_tokens": usage.get("total_tokens", 0),
        "token_usage": usage,
        "created_at": time.time(),
    }

def _extractor_messages(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]

def build_prompt_payload(
    input_text: str,
    base_rows: List[Dict[str, Any]],
    *,
    session_id: Optional[str] = None,
    kb_revision: int = 0,
) -> Dict[str, Any]:
    return {
        "task": "Extract ontology-valid Wikibase-like rows and a reasoning/change report",
        "source_text": normalize_input_text(input_text),
        "ontology": compact_ontology_for_prompt(),
        "required_output_schema": REQUIRED_OUTPUT_SCHEMA,
        **_build_kb_prompt_context(
            input_text,
            base_rows,
            session_id=session_id,
            kb_revision=kb_revision,
        ),
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
        temperature=EXTRACTOR_TEMPERATURE,
        response_format={"type": "json_object"},
        messages=_extractor_messages(payload),
    )
    content = response.choices[0].message.content or "{}"
    try:
        return json.loads(content), token_usage(response)
    except Exception as exc:
        raise RuntimeError(f"Extractor returned invalid JSON: {exc}\nRaw: {content[:1000]}")

def generate_proposal(
    input_text: str,
    base_rows: List[Dict[str, Any]],
    *,
    session_id: Optional[str] = None,
    kb_revision: int = 0,
) -> Dict[str, Any]:
    started = time.perf_counter()
    llm_out, usage = call_extractor(
        input_text=input_text,
        base_rows=base_rows,
        session_id=session_id,
        kb_revision=kb_revision,
    )
    proposal_rows, raw_changes, warnings = validate_llm_output(llm_out)
    # Resolve NEW:* placeholders silently (avoid surfacing as "validation warnings" in the UI).
    proposal_rows = resolve_existing_entities(proposal_rows, base_rows, warnings=None)
    merged = merge_proposal_into_base(base_rows, proposal_rows, raw_changes)
    reasoning = normalize_reasoning_report(raw_changes, proposal_rows, warnings + list(merged.get("warnings", [])))
    generation_seconds = round(time.perf_counter() - started, 3)
    proposal = _build_proposal_record(
        merged,
        proposal_rows,
        reasoning,
        usage,
        generation_seconds,
        session_id=session_id,
        kb_revision=kb_revision,
    )
    PROPOSALS[proposal["proposal_id"]] = proposal
    return proposal