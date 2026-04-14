"""Validation, merge, and reasoning-report helpers for LLM extraction results."""

from collections import Counter
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from ..core.config import ALLOW_DELETE
from ..state import canonical_row_key, dedupe_rows, normalize_key_value
from .ontology import ONTOLOGY, STATEMENT_FIELDS, clean_statement_row
CHANGE_ACTIONS = ("create", "edit", "link", "delete", "uncertain")
MODEL_CONSTRUCT_PROPERTY_LABELS = (
    "instance of Class",
    "subclass of Class",
    "particular of model construct",
    "universal of model construct",
)
INSTANCE_OF_CLASS_LABELS = ("instance of Class", "particular of model construct")
SUBCLASS_OF_CLASS_LABELS = ("subclass of Class", "universal of model construct")
SOURCE_PROPERTY_LABELS = ("described by", "declared by")
RULE_LIKE_CLASS_LABELS = {
    "Structural Rule",
    "Operational Rule",
    "Organisational Rule",
    "Interpretative Rule",
    "Evaluative Rule",
    "Rule",
}
DECLARATIVE_SOURCE_CLASS_LABELS = {
    "Declarative Rule Description",
    "Description Section",
    "Description Collection",
}

def compact_evidence(evidence_list: Any) -> List[str]:
    raw = [
        snippet.strip()
        for snippet in (
            e.get("snippet") if isinstance(e, dict) else None
            for e in (evidence_list or [])
        )
        if isinstance(snippet, str) and snippet.strip()
    ]

    def norm_snippet(snippet: str) -> str:
        snippet = " ".join(snippet.lower().split())
        snippet = re.sub(r"[^a-z0-9 ]+", "", snippet)
        return snippet.strip()

    def near_duplicate(a: str, b: str) -> bool:
        if not a or not b:
            return False
        if a == b:
            return True
        if a in b or b in a:
            shorter = min(len(a), len(b))
            longer = max(len(a), len(b))
            return (shorter / longer) >= 0.65
        return SequenceMatcher(None, a, b).ratio() >= 0.92

    deduped: List[str] = []
    deduped_norm: List[str] = []
    for snippet in raw:
        normalized = norm_snippet(snippet)
        if not normalized:
            continue

        replaced = False
        skip = False
        for index, existing in enumerate(deduped_norm):
            if not near_duplicate(existing, normalized):
                continue
            if len(snippet) > len(deduped[index]):
                deduped[index] = snippet
                deduped_norm[index] = normalized
                replaced = True
            skip = True
            break

        if replaced or skip:
            continue
        deduped.append(snippet)
        deduped_norm.append(normalized)

    return deduped[:6]

def statement_parts(row: Any) -> Tuple[str, Optional[str]]:
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
    statement = f"{prop_label} -> {value_text}" if value_text else prop_label
    qprop = row.get("qualifierPropertyLabel") or row.get("qualifierProperty")
    qval = row.get("qualifierValueLabel") or row.get("qualifierValue")
    if qprop and qval:
        statement += f" [qualifier: {qprop} -> {qval}]"
    return subject, statement

def what_label(action: str, entity_scope: Any) -> str:
    if action == "create":
        return "Create entity" if entity_scope == "entity" else "Create statement"
    if action == "edit":
        return "Edit"
    if action == "link":
        return "Link to existing entity"
    if action == "delete":
        return "Delete"
    return "Needs review"

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
    for index, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            warnings.append(f"proposed_rows[{index}] ignored (not an object)")
            continue
        cleaned = clean_statement_row(row)
        if not cleaned:
            warnings.append(f"proposed_rows[{index}] ignored (missing fields or invalid property)")
            continue
        valid_rows.append(cleaned)

    return dedupe_rows(valid_rows), raw_changes, warnings

def _property_uri_for_label(label: str) -> Optional[str]:
    target = normalize_key_value(label)
    property_labels = ONTOLOGY.index.get("property_labels", {})
    exact = property_labels.get(target)
    if exact:
        return exact
    for existing_label_key, entity in property_labels.items():
        if isinstance(existing_label_key, str) and target and target in existing_label_key:
            return entity
    return None

def _placeholder_subject_groups(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = row.get("item")
        if isinstance(item, str) and item.startswith("NEW:"):
            out.setdefault(item, []).append(row)
    return out

def _row_property_label(row: Dict[str, Any]) -> str:
    return str(row.get("propertyLabel") or row.get("property") or "").strip()

def _row_uses_property_label(row: Dict[str, Any], labels: Tuple[str, ...]) -> bool:
    property_uri = row.get("property")
    property_label = _row_property_label(row)
    normalized_labels = {normalize_key_value(label) for label in labels}
    if normalize_key_value(property_label) in normalized_labels:
        return True
    for label in labels:
        uri = _property_uri_for_label(label)
        if uri and normalize_key_value(property_uri) == normalize_key_value(uri):
            return True
    return False

def _subject_preview_label(rows: List[Dict[str, Any]], subject: str) -> str:
    for row in rows:
        label = row.get("itemLabel")
        if isinstance(label, str) and label.strip():
            return label.strip()
    return subject

def _subject_model_class_labels(rows: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for row in rows:
        if not _row_uses_property_label(row, MODEL_CONSTRUCT_PROPERTY_LABELS):
            continue
        label = row.get("valueLabel")
        if isinstance(label, str) and label.strip() and label.strip() not in out:
            out.append(label.strip())
    return out

def augment_new_item_source_rows(
    rows: List[Dict[str, Any]],
    source_candidate: Optional[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    if not source_candidate:
        return rows, []

    source_entity = source_candidate.get("entity")
    source_label = source_candidate.get("label") or source_entity
    if not isinstance(source_entity, str) or not source_entity.strip():
        return rows, []

    described_by_uri = _property_uri_for_label("described by")
    declared_by_uri = _property_uri_for_label("declared by")
    if not described_by_uri:
        return rows, []

    augmented = list(rows)
    warnings: List[str] = []
    source_class_labels = {
        str(label).strip()
        for label in (source_candidate.get("class_labels") or [])
        if isinstance(label, str) and label.strip()
    }

    for subject, subject_rows in _placeholder_subject_groups(rows).items():
        if any(_row_uses_property_label(row, SOURCE_PROPERTY_LABELS) for row in subject_rows):
            continue

        subject_classes = set(_subject_model_class_labels(subject_rows))
        use_declared_by = bool(
            declared_by_uri
            and subject_classes.intersection(RULE_LIKE_CLASS_LABELS)
            and source_class_labels.intersection(DECLARATIVE_SOURCE_CLASS_LABELS)
        )
        property_label = "declared by" if use_declared_by else "described by"
        property_uri = declared_by_uri if use_declared_by else described_by_uri
        if not property_uri:
            continue

        augmented.append({
            "item": subject,
            "itemLabel": _subject_preview_label(subject_rows, subject),
            "property": property_uri,
            "propertyLabel": property_label,
            "value": source_entity,
            "valueLabel": source_label,
        })
        warnings.append(
            f'Added `{property_label}` for new item "{_subject_preview_label(subject_rows, subject)}" using source "{source_label}".'
        )

    return dedupe_rows(augmented), warnings

def validate_required_new_item_rows(
    rows: List[Dict[str, Any]],
    *,
    require_source: bool = False,
) -> List[str]:
    warnings: List[str] = []
    for subject, subject_rows in _placeholder_subject_groups(rows).items():
        subject_label = _subject_preview_label(subject_rows, subject)
        model_rows = [row for row in subject_rows if _row_uses_property_label(row, MODEL_CONSTRUCT_PROPERTY_LABELS)]
        if not model_rows:
            warnings.append(
                f'New item "{subject_label}" is missing a required model row (`instance of Class` or `subclass of Class`).'
            )
        elif any(_row_uses_property_label(row, INSTANCE_OF_CLASS_LABELS) for row in model_rows) and any(
            _row_uses_property_label(row, SUBCLASS_OF_CLASS_LABELS) for row in model_rows
        ):
            warnings.append(
                f'New item "{subject_label}" has both `instance of Class` and `subclass of Class`; review which one should remain.'
            )

        if require_source and not any(_row_uses_property_label(row, SOURCE_PROPERTY_LABELS) for row in subject_rows):
            warnings.append(
                f'New item "{subject_label}" is missing a required source row (`described by` or `declared by`).'
            )

    return warnings

def _same_normalized_value(a: Any, b: Any) -> bool:
    a_value = normalize_key_value(a)
    b_value = normalize_key_value(b)
    return a_value is not None and a_value == b_value

def _row_matches_target_ref(row: Dict[str, Any], target_ref: Any) -> bool:
    if target_ref is None:
        return False
    for field in STATEMENT_FIELDS:
        if _same_normalized_value(row.get(field), target_ref):
            return True
    return False


def _same_field_or_label(row: Dict[str, Any], proposal_row: Dict[str, Any], field: str, label_field: str) -> bool:
    return _same_normalized_value(row.get(field), proposal_row.get(field)) or _same_normalized_value(
        row.get(label_field), proposal_row.get(label_field)
    )

def _match_score(
    row: Dict[str, Any],
    proposal_row: Dict[str, Any],
    field: str,
    label_field: str,
    *,
    exact_points: int,
    label_points: int,
) -> int:
    if _same_normalized_value(row.get(field), proposal_row.get(field)):
        return exact_points
    if _same_normalized_value(row.get(label_field), proposal_row.get(label_field)):
        return label_points
    return 0

def _proposal_row_for_change(change: Dict[str, Any], proposal_rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    index = change.get("proposed_row_index")
    if not isinstance(index, int) or not (0 <= index < len(proposal_rows)):
        return None
    return proposal_rows[index]

def _iter_action_changes(changes: List[Dict[str, Any]], action: str):
    for change in changes:
        if isinstance(change, dict) and change.get("action") == action:
            yield change

def _edit_match_candidates(
    base_rows: List[Dict[str, Any]],
    proposal_row: Dict[str, Any],
    *,
    target_ref: Any = None,
    unavailable_keys: Optional[set] = None,
) -> List[Dict[str, Any]]:
    unavailable_keys = unavailable_keys or set()
    proposal_key = canonical_row_key(proposal_row)
    candidates: List[Dict[str, Any]] = []

    for row in base_rows:
        if not isinstance(row, dict):
            continue
        row_key = canonical_row_key(row)
        if row_key in unavailable_keys or row_key == proposal_key:
            continue

        same_item = _same_field_or_label(row, proposal_row, "item", "itemLabel")
        same_property = _same_field_or_label(row, proposal_row, "property", "propertyLabel")
        target_match = _row_matches_target_ref(row, target_ref)
        if not ((same_item and same_property) or (same_property and target_match)):
            continue
        candidates.append(row)

    return candidates

def _select_edit_base_row(
    base_rows: List[Dict[str, Any]],
    proposal_row: Dict[str, Any],
    *,
    target_ref: Any = None,
    unavailable_keys: Optional[set] = None,
) -> Optional[Dict[str, Any]]:
    ranked: List[Tuple[int, Dict[str, Any]]] = []

    for row in _edit_match_candidates(
        base_rows,
        proposal_row,
        target_ref=target_ref,
        unavailable_keys=unavailable_keys,
    ):
        target_match = _row_matches_target_ref(row, target_ref)
        score = (
            (12 if target_match else 0)
            + _match_score(row, proposal_row, "item", "itemLabel", exact_points=10, label_points=4)
            + _match_score(row, proposal_row, "property", "propertyLabel", exact_points=10, label_points=4)
            + _match_score(row, proposal_row, "qualifierProperty", "qualifierPropertyLabel", exact_points=4, label_points=2)
            + _match_score(row, proposal_row, "value", "valueLabel", exact_points=1, label_points=1)
            + _match_score(row, proposal_row, "qualifierValue", "qualifierValueLabel", exact_points=1, label_points=1)
        )
        ranked.append((score, row))

    if not ranked:
        return None

    ranked.sort(key=lambda item: item[0], reverse=True)
    best_score, best_row = ranked[0]
    # Edit matching is intentionally conservative: a missed edit becomes a warning,
    # while a wrong edit would silently overwrite the wrong existing statement.
    if best_score < 14:
        return None
    if len(ranked) > 1 and ranked[1][0] == best_score:
        return None
    return best_row

def _collect_delete_actions(
    base_rows_by_key: Dict[Any, Dict[str, Any]],
    proposal_rows: List[Dict[str, Any]],
    changes: List[Dict[str, Any]],
) -> Tuple[set, set, List[Dict[str, Any]]]:
    delete_keys = set()
    delete_proposal_keys = set()
    deleted_rows: List[Dict[str, Any]] = []

    if not ALLOW_DELETE:
        return delete_keys, delete_proposal_keys, deleted_rows

    for change in _iter_action_changes(changes, "delete"):
        proposal_row = _proposal_row_for_change(change, proposal_rows)
        if proposal_row is None:
            continue
        row_key = canonical_row_key(proposal_row)
        delete_proposal_keys.add(row_key)
        if row_key in base_rows_by_key and row_key not in delete_keys:
            delete_keys.add(row_key)
            deleted_rows.append(dict(base_rows_by_key[row_key]))

    return delete_keys, delete_proposal_keys, deleted_rows

def _collect_edit_actions(
    base_rows: List[Dict[str, Any]],
    base_keys: set,
    proposal_rows: List[Dict[str, Any]],
    changes: List[Dict[str, Any]],
    unavailable_keys: set,
) -> Tuple[List[Dict[str, Dict[str, Any]]], set, set, List[str]]:
    edited_rows: List[Dict[str, Dict[str, Any]]] = []
    replaced_keys = set()
    blocked_proposal_indices = set()
    merge_warnings: List[str] = []
    warned_indices = set()

    for change in _iter_action_changes(changes, "edit"):
        proposal_index = change.get("proposed_row_index")
        proposal_row = _proposal_row_for_change(change, proposal_rows)
        if proposal_row is None:
            continue
        proposal_key = canonical_row_key(proposal_row)
        if proposal_key in base_keys:
            continue

        matched = _select_edit_base_row(
            base_rows,
            proposal_row,
            target_ref=change.get("target_ref"),
            unavailable_keys=unavailable_keys | replaced_keys,
        )
        if matched is None:
            if isinstance(proposal_index, int):
                # Prevent unmatched "edit" rows from later falling through as plain adds;
                # otherwise the same intent would mutate from edit to create implicitly.
                blocked_proposal_indices.add(proposal_index)
                if proposal_index not in warned_indices:
                    warned_indices.add(proposal_index)
                    subject, statement_preview = statement_parts(proposal_row)
                    candidate_count = len(_edit_match_candidates(
                        base_rows,
                        proposal_row,
                        target_ref=change.get("target_ref"),
                        unavailable_keys=unavailable_keys | replaced_keys,
                    ))
                    if candidate_count == 0:
                        merge_warnings.append(
                            f"Skipped edit for {subject}: no existing row looked editable for {statement_preview}. This was probably a new statement and should be modeled as `create` instead of `edit`."
                        )
                    else:
                        merge_warnings.append(
                            f"Skipped edit for {subject}: could not uniquely match an existing row for {statement_preview}."
                        )
            continue

        before_key = canonical_row_key(matched)
        replaced_keys.add(before_key)
        edited_rows.append({"before": dict(matched), "after": dict(proposal_row)})

    return edited_rows, replaced_keys, blocked_proposal_indices, merge_warnings

def _append_added_rows(
    kept_rows: List[Dict[str, Any]],
    proposal_rows: List[Dict[str, Any]],
    *,
    base_keys: set,
    blocked_proposal_indices: set,
    edited_after_keys: set,
    delete_proposal_keys: set,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    added_rows = []
    added_keys = set()
    duplicate_warnings: List[str] = []
    warned_base_keys = set()
    for index, row in enumerate(proposal_rows):
        if index in blocked_proposal_indices:
            continue
        row_key = canonical_row_key(row)
        if row_key in base_keys:
            if row_key not in warned_base_keys:
                warned_base_keys.add(row_key)
                subject, statement_preview = statement_parts(row)
                duplicate_warnings.append(
                    f"Omitted proposed row for {subject}: {statement_preview} already exists in the KB."
                )
            continue
        if row_key in edited_after_keys or row_key in added_keys or row_key in delete_proposal_keys:
            continue
        kept_rows.append(row)
        added_rows.append(row)
        added_keys.add(row_key)
    return added_rows, duplicate_warnings

def merge_proposal_into_base(base_rows, proposal_rows, changes):
    base_dict_rows = [row for row in base_rows if isinstance(row, dict)]
    base_keys = {canonical_row_key(row) for row in base_dict_rows}
    base_rows_by_key = {
        canonical_row_key(row): row
        for row in base_dict_rows
    }
    delete_keys, delete_proposal_keys, deleted_rows = _collect_delete_actions(base_rows_by_key, proposal_rows, changes)
    edited_rows, replaced_keys, blocked_proposal_indices, merge_warnings = _collect_edit_actions(
        base_dict_rows,
        base_keys,
        proposal_rows,
        changes,
        unavailable_keys=delete_keys,
    )

    removed_keys = delete_keys | replaced_keys
    kept_rows = [row for row in base_dict_rows if canonical_row_key(row) not in removed_keys]

    edited_after_keys = set()
    for entry in edited_rows:
        after_row = entry["after"]
        edited_after_keys.add(canonical_row_key(after_row))
        # Edited rows replace the matched base row before generic add handling runs.
        kept_rows.append(after_row)

    added_rows, add_warnings = _append_added_rows(
        kept_rows,
        proposal_rows,
        base_keys=base_keys,
        blocked_proposal_indices=blocked_proposal_indices,
        edited_after_keys=edited_after_keys,
        delete_proposal_keys=delete_proposal_keys,
    )

    return {
        "merged_rows": dedupe_rows(kept_rows),
        "diff": {
            "added_rows": added_rows,
            "edited_rows": edited_rows,
            "deleted_rows": deleted_rows,
        },
        "warnings": merge_warnings + add_warnings,
    }

def _normalized_action(action: Any) -> str:
    return str(action) if action in CHANGE_ACTIONS else "uncertain"

def _reasoning_change_entry(change: Dict[str, Any], proposal_row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    evidence = change.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = []
    subject, statement_preview = statement_parts(proposal_row)
    return {
        "what": what_label(_normalized_action(change.get("action", "uncertain")), change.get("entity_scope", "statement")),
        "subject": subject,
        "statement": statement_preview,
        "why": ("" if change.get("justification", "") is None else str(change.get("justification", ""))).strip(),
        "evidence": compact_evidence(evidence),
        "confidence": change.get("confidence", 0.0),
        "relevance": change.get("relevance_score", None),
        "needs_review": change.get("review_flag"),
    }

def normalize_reasoning_report(raw_changes, proposal_rows, validation_warnings):
    counts = Counter()
    changes_out = []
    for change in raw_changes:
        if not isinstance(change, dict):
            continue
        action = _normalized_action(change.get("action", "uncertain"))
        counts[action] += 1

        proposed_row = _proposal_row_for_change(change, proposal_rows)
        changes_out.append(_reasoning_change_entry(change, proposed_row))

    return {
        "summary": {
            "creates": counts.get("create", 0),
            "edits": counts.get("edit", 0),
            "links": counts.get("link", 0),
            "deletes": counts.get("delete", 0),
            "uncertain": counts.get("uncertain", 0),
            "validation_warnings": len(validation_warnings),
        },
        "validation_warnings": validation_warnings,
        "proposed_changes": changes_out,
    }
