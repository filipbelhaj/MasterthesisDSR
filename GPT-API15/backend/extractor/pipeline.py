"""End-to-end proposal generation pipeline around retrieval, prompting, and packaging."""

import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
from ..core.config import (
    ENTITY_CATALOG_LIMIT,
    EXTRACTOR_MODEL,
    EXTRACTOR_ROW_BUDGET_PREFERRED_MAX,
    EXTRACTOR_ROW_BUDGET_PREFERRED_MIN,
    EXTRACTOR_TEMPERATURE,
    TOPK,
    get_client,
)
from ..state import PROPOSALS, dedupe_rows
from ..core.prompt import SYSTEM_PROMPT
from .context import (
    entity_ids_from_catalog,
    existing_actor_catalog_for_input,
    existing_entity_catalog_for_input,
    existing_item_labels,
    normalize_input_text,
    resolve_existing_entities,
    select_preview_rows,
    source_candidates_for_input,
    structured_reference_style_examples,
)
from .ontology import ONTOLOGY, compact_ontology_for_prompt
from .ontology_rules import (
    DISALLOWED_EXTRACTOR_PROPERTY_NOTE,
    disallowed_extractor_properties,
    format_backticked_or_list,
)
from .shapes import SHAPE_CONSTRAINTS_NOTE, compact_shapes_for_prompt
from .postprocess import (
    augment_row_references,
    augment_new_item_source_rows,
    merge_proposal_into_base,
    normalize_reasoning_report,
    validate_llm_output,
    validate_required_new_item_rows,
)

REQUIRED_OUTPUT_SCHEMA = {
    "proposed_rows": [{
        "item": "string URI or provisional NEW:entity_x",
        "itemLabel": "string",
        "property": "ontology property URI only",
        "propertyLabel": "string",
        "value": "entity URI/id or literal",
        "valueLabel": "optional string",
        "qualifierProperty": "optional ontology property URI only",
        "qualifierPropertyLabel": "optional string",
        "qualifierValue": "optional entity URI/id or literal",
        "qualifierValueLabel": "optional string",
        "references": [{
            "property": "ontology property URI only",
            "propertyLabel": "string",
            "value": "existing entity URI/id, or grounded source title/URL string when no existing source entity is available",
            "valueLabel": "optional string",
        }],
    }],
    "changes": [{
        "id": "chg_001",
        "action": "create|edit|delete",
        "entity_scope": "statement|entity",
        "target_ref": "existing URI or row-ref",
        "proposed_row_index": 0,
        "justification": "why this was proposed",
        "evidence": [{"snippet": "source snippet", "start_char": 0, "end_char": 20}],
        "confidence": 0.0,
        "relevance_score": 0.0,
        "review_flag": "optional flag or null",
    }],
}
OUTPUT_CONSTRAINTS = {
    "top_level_keys": ["proposed_rows", "changes"],
    "allowed_change_actions": ["create", "edit", "delete"],
    "row_budget_hint": {
        "preferred_min": EXTRACTOR_ROW_BUDGET_PREFERRED_MIN,
        "preferred_max": EXTRACTOR_ROW_BUDGET_PREFERRED_MAX,
        "policy": "Soft guidance only. Exceed the preferred range when the extra rows are clearly grounded and high value.",
    },
    "field_rules": {
        "property": "Must be an ontology property URI, never a property label or bare P-id.",
        "qualifierProperty": "Must be an ontology property URI when present.",
        "item": "Use an existing entity URI/id or a provisional NEW:entity_x token only for a new subject item.",
        "value": "Use an entity URI/id when the value is an entity; never use NEW:* here.",
        "qualifierValue": "Use an entity URI/id when the qualifier value is an entity; never use NEW:* here.",
        "labels": "itemLabel/valueLabel/qualifierValueLabel are human-readable labels and never substitutes for ids.",
        "qualifiers": "Each row can contain at most one qualifier pair.",
        "references": (
            "Optional. When present, use one or more source references as property-value pairs. "
            f"Allowed reference properties are {format_backticked_or_list(('described by', 'declared by', 'defined by'))} only. "
            "Prefer an existing entity id/URI in `value`; if no existing source entity is available, "
            "a grounded source title or URL string may be used instead."
        ),
        "changes": "Use exactly one change entry per proposed row, with zero-based proposed_row_index.",
    },
    "source_link_policy": (
        "If existing_kb_source_candidates is ambiguous, omit item-level source rows and statement references instead of guessing."
    ),
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
ITEM_LABEL_SAMPLE_NOTE = (
    "Existing item labels that appear relevant to the source text. Treat this as a duplicate-warning "
    "list, not as proof that every matching label is the same entity."
)
SOURCE_CANDIDATE_NOTE = (
    "Existing KB entities that look like source documents/sections and are explicitly mentioned "
    "in the input. Reuse these for `described by`/`declared by` rows when grounding new items only "
    "when one candidate is clearly the right source; otherwise omit the source row rather than guess."
)
ACTOR_CATALOG_NOTE = (
    "Actor entities already present in the KB and mentioned in the source text. Reuse these actors "
    "instead of creating duplicates."
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
) -> Tuple[Dict[str, Any], List[str]]:
    entity_catalog = existing_entity_catalog_for_input(input_text, base_rows, limit=ENTITY_CATALOG_LIMIT)
    actor_catalog = existing_actor_catalog_for_input(input_text, base_rows, limit=24)
    source_candidates = source_candidates_for_input(input_text, base_rows, limit=8)
    matched_entity_ids = entity_ids_from_catalog(entity_catalog)
    retrieval_warnings: List[str] = []
    return {
        "existing_kb_preview_rows": select_preview_rows(
            input_text,
            base_rows,
            TOPK,
            session_id=session_id,
            kb_revision=kb_revision,
            matched_entity_ids=matched_entity_ids,
            warnings=retrieval_warnings,
        ),
        "existing_kb_preview_note": "Rows are retrieved from the existing KB for relevance to the source text; do not assume they are exhaustive.",
        "existing_kb_entity_catalog": entity_catalog,
        "existing_kb_entity_catalog_note": ENTITY_CATALOG_NOTE,
        "existing_kb_actor_catalog": actor_catalog,
        "existing_kb_actor_catalog_note": ACTOR_CATALOG_NOTE,
        "existing_kb_source_candidates": source_candidates,
        "existing_kb_source_candidates_note": SOURCE_CANDIDATE_NOTE,
        "existing_kb_structured_reference_examples": structured_reference_style_examples(entity_catalog, base_rows),
        "existing_kb_structured_reference_examples_note": STRUCTURED_REFERENCE_NOTE,
        "existing_kb_item_labels_sample": existing_item_labels(input_text, base_rows),
        "existing_kb_item_labels_sample_note": ITEM_LABEL_SAMPLE_NOTE,
    }, retrieval_warnings

def _edited_after_rows(merged: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        entry["after"]
        for entry in merged["diff"]["edited_rows"]
        if isinstance(entry, dict) and isinstance(entry.get("after"), dict)
    ]

def _entity_reuse_warnings(
    original_rows: List[Dict[str, Any]],
    resolved_rows: List[Dict[str, Any]],
) -> List[str]:
    warnings: List[str] = []
    seen: set[tuple[str, str]] = set()

    for before, after in zip(original_rows, resolved_rows):
        if not isinstance(before, dict) or not isinstance(after, dict):
            continue
        before_item = before.get("item")
        after_item = after.get("item")
        if not (isinstance(before_item, str) and before_item.startswith("NEW:")):
            continue
        if not isinstance(after_item, str) or after_item.startswith("NEW:") or before_item == after_item:
            continue

        key = (before_item, after_item)
        if key in seen:
            continue
        seen.add(key)

        label = str(after.get("itemLabel") or before.get("itemLabel") or after_item).strip() or after_item
        warnings.append(
            f'Reused existing entity "{label}" as {after_item} instead of creating a new item.'
        )

    return warnings

def _build_proposal_record(
    merged: Dict[str, Any],
    proposal_rows: List[Dict[str, Any]],
    reasoning: Dict[str, Any],
    usage: Dict[str, int],
    generation_seconds: float,
    retrieval_warnings: List[str],
    modeling_warnings: List[str],
    session_id: Optional[str] = None,
    kb_revision: int = 0,
    inferred_source: Optional[Dict[str, Any]] = None,
    user_extraction_instruction: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "proposal_id": f"prop_{uuid.uuid4().hex[:10]}",
        "session_id": session_id,
        "kb_revision": kb_revision,
        "user_extraction_instruction": user_extraction_instruction,
        # Approve applies a patch, not the full preview graph, so edited rows are stored
        # as their final "after" form alongside truly new rows.
        "patch_kb_json": dedupe_rows(merged["diff"]["added_rows"] + _edited_after_rows(merged)),
        "proposed_kb_json": merged["merged_rows"],
        "reasoning_report": reasoning,
        "diff": merged["diff"],
        "proposal_rows_only": proposal_rows,
        "generation_seconds": generation_seconds,
        "generation_tokens": usage.get("total_tokens", 0),
        "token_usage": usage,
        "retrieval_warnings": retrieval_warnings,
        "modeling_warnings": modeling_warnings,
        "requires_source_links": bool(inferred_source),
        "required_source_entity": inferred_source.get("entity") if isinstance(inferred_source, dict) else None,
        "required_source_label": inferred_source.get("label") if isinstance(inferred_source, dict) else None,
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
    user_extraction_instruction: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    kb_context, retrieval_warnings = _build_kb_prompt_context(
        input_text,
        base_rows,
        session_id=session_id,
        kb_revision=kb_revision,
    )
    return {
        "task": "Extract ontology-valid Wikibase-like rows and a reasoning/change report",
        "source_text": normalize_input_text(input_text),
        "user_extraction_instruction": (user_extraction_instruction or "").strip(),
        "ontology": compact_ontology_for_prompt(),
        "shape_constraints": compact_shapes_for_prompt(),
        "shape_constraints_note": SHAPE_CONSTRAINTS_NOTE,
        "disallowed_extractor_properties": disallowed_extractor_properties(ONTOLOGY.index),
        "disallowed_extractor_properties_note": DISALLOWED_EXTRACTOR_PROPERTY_NOTE,
        "required_output_schema": REQUIRED_OUTPUT_SCHEMA,
        "output_constraints": OUTPUT_CONSTRAINTS,
        **kb_context,
    }, retrieval_warnings

def call_extractor(
    input_text: str,
    base_rows: List[Dict[str, Any]],
    *,
    session_id: Optional[str] = None,
    kb_revision: int = 0,
    user_extraction_instruction: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, int], List[str]]:
    if ONTOLOGY.load_error:
        raise RuntimeError(f"Failed to load ontology: {ONTOLOGY.load_error}")

    payload, retrieval_warnings = build_prompt_payload(
        input_text,
        base_rows,
        session_id=session_id,
        kb_revision=kb_revision,
        user_extraction_instruction=user_extraction_instruction,
    )
    response = get_client().chat.completions.create(
        model=EXTRACTOR_MODEL,
        temperature=EXTRACTOR_TEMPERATURE,
        response_format={"type": "json_object"},
        messages=_extractor_messages(payload),
    )
    content = response.choices[0].message.content or "{}"
    try:
        return json.loads(content), token_usage(response), retrieval_warnings
    except Exception as exc:
        raise RuntimeError(f"Extractor returned invalid JSON: {exc}\nRaw: {content[:1000]}")

def generate_proposal(
    input_text: str,
    base_rows: List[Dict[str, Any]],
    *,
    session_id: Optional[str] = None,
    kb_revision: int = 0,
    user_extraction_instruction: Optional[str] = None,
) -> Dict[str, Any]:
    started = time.perf_counter()
    cleaned_user_instruction = (user_extraction_instruction or "").strip()
    inferred_source_candidates = source_candidates_for_input(input_text, base_rows, limit=2)
    inferred_source = inferred_source_candidates[0] if len(inferred_source_candidates) == 1 else None
    llm_out, usage, retrieval_warnings = call_extractor(
        input_text=input_text,
        base_rows=base_rows,
        session_id=session_id,
        kb_revision=kb_revision,
        user_extraction_instruction=cleaned_user_instruction,
    )
    proposal_rows, raw_changes, warnings = validate_llm_output(llm_out, base_rows=base_rows)
    # This pass quietly reuses known entity ids where labels/placeholders can be aligned,
    # which keeps the UI focused on real review issues rather than normalization noise.
    original_proposal_rows = [dict(row) for row in proposal_rows]
    proposal_rows = resolve_existing_entities(proposal_rows, base_rows)
    warnings = warnings + _entity_reuse_warnings(original_proposal_rows, proposal_rows)
    proposal_rows, reference_warnings = augment_row_references(
        proposal_rows,
        inferred_source,
        base_rows=base_rows,
    )
    warnings = warnings + reference_warnings
    proposal_rows, source_fill_warnings = augment_new_item_source_rows(proposal_rows, inferred_source)
    warnings = warnings + source_fill_warnings
    modeling_warnings = validate_required_new_item_rows(
        proposal_rows,
        require_source=bool(inferred_source),
    )
    warnings = warnings + modeling_warnings
    merged = merge_proposal_into_base(base_rows, proposal_rows, raw_changes)
    reasoning = normalize_reasoning_report(raw_changes, proposal_rows, warnings + list(merged.get("warnings", [])))
    generation_seconds = round(time.perf_counter() - started, 3)
    proposal = _build_proposal_record(
        merged,
        proposal_rows,
        reasoning,
        usage,
        generation_seconds,
        retrieval_warnings,
        modeling_warnings + source_fill_warnings + reference_warnings,
        session_id=session_id,
        kb_revision=kb_revision,
        inferred_source=inferred_source,
        user_extraction_instruction=cleaned_user_instruction,
    )
    PROPOSALS[proposal["proposal_id"]] = proposal
    return proposal
