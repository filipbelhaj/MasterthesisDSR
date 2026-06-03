"""Ontology profile adapter, validation, and prompt/export helpers.

User-editable ontology values live in `ontology_profile.py`. This module keeps
the stable constants/functions consumed by the extraction pipeline.
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .ontology_profile import (
    CLASSIFICATION_PROPERTY_LABELS,
    CONTEXT_MODEL_CONSTRUCT_PROPERTY_LABELS,
    CREATION_CONTEXT_PROPERTY_LABEL,
    CREATION_CONTEXT_VALUE_PREFIX,
    DECLARATIVE_SOURCE_CLASS_LABELS,
    DECLARED_BY_LABEL,
    DEFINED_BY_LABEL,
    DESCRIBED_BY_LABEL,
    DESCRIPTIVE_SOURCE_CLASS_LABELS,
    DISALLOWED_EXTRACTOR_PROPERTY_IDS,
    ENTITY_BASE_URI,
    INSTANCE_OF_CLASS_LABELS,
    MODEL_CONSTRUCT_PROPERTY_LABELS,
    PRIORITIZED_CONCEPT_LABELS,
    REFERENCE_ALLOWED_CLASS_LABELS,
    REFERENCE_PROPERTY_LABELS,
    RULE_LIKE_CLASS_LABELS,
    SHAPE_DEFINITIONS,
    SOURCE_LIKE_MODEL_CONSTRUCT_LABELS,
    SOURCE_LIKE_MODEL_CONSTRUCT_PRIORITY,
    SOURCE_PROPERTY_LABELS,
    SUBCLASS_OF_CLASS_LABELS,
)

DISALLOWED_EXTRACTOR_PROPERTY_NOTE = (
    "These ontology properties exist in the KB but are blocked for extractor output because "
    "they are often misunderstood, too meta-level, or lower-value for this workflow. "
    "Do not use them in `property` or `qualifierProperty`."
)

NEW_ITEM_PLACEHOLDER_PREFIX = "NEW:"
NEW_ITEM_PLACEHOLDER_STEM = "entity"
NEW_ITEM_PLACEHOLDER_PATTERN = rf"^{re.escape(NEW_ITEM_PLACEHOLDER_PREFIX)}{NEW_ITEM_PLACEHOLDER_STEM}_(\d+)$"

SHAPE_CONSTRAINTS_NOTE = (
    "These shapes are extra modeling guidance derived from the ontology. Apply them when they "
    "fit a subject you create or edit, but do not treat unchanged existing KB rows as invalid "
    "just because they are outside these shapes."
)


def format_backticked_or_list(labels: Tuple[str, ...]) -> str:
    """Format labels as a backticked English `or` list.

    Args:
        labels: Labels to format.

    Returns:
        A readable list string for prompt text.
    """
    quoted = [f"`{label}`" for label in labels]
    if not quoted:
        return ""
    if len(quoted) == 1:
        return quoted[0]
    if len(quoted) == 2:
        return f"{quoted[0]} or {quoted[1]}"
    return ", ".join(quoted[:-1]) + f", or {quoted[-1]}"


def format_plain_or_list(labels: Tuple[str, ...]) -> str:
    """Format labels as a plain English `or` list.

    Args:
        labels: Labels to format.

    Returns:
        A readable list string for plain text.
    """
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} or {labels[1]}"
    return ", ".join(labels[:-1]) + f", or {labels[-1]}"


def reference_property_labels_preview() -> str:
    """Return the allowed reference-property labels as backticked prompt text."""
    return format_backticked_or_list(REFERENCE_PROPERTY_LABELS)


def source_property_labels_preview() -> str:
    """Return the source-property labels as backticked prompt text."""
    return format_backticked_or_list(SOURCE_PROPERTY_LABELS)


def prioritized_concept_labels_preview() -> str:
    """Return prioritized extraction concept labels as plain prompt text."""
    return format_plain_or_list(tuple(PRIORITIZED_CONCEPT_LABELS.values()))


def actor_class_labels_preview() -> str:
    """Return actor-like class labels as backticked prompt text."""
    return format_backticked_or_list(actor_class_labels())


def broad_placeholder_class_labels_preview() -> str:
    """Return broad placeholder class labels as backticked prompt text."""
    return format_backticked_or_list(broad_placeholder_class_labels())


def model_construct_property_labels_preview() -> str:
    """Return modeling-property labels as backticked prompt text."""
    return format_backticked_or_list(MODEL_CONSTRUCT_PROPERTY_LABELS)


def instance_of_class_labels_preview() -> str:
    """Return instance-style classification labels as backticked prompt text."""
    return format_backticked_or_list(INSTANCE_OF_CLASS_LABELS)


def subclass_of_class_labels_preview() -> str:
    """Return subclass-style classification labels as backticked prompt text."""
    return format_backticked_or_list(SUBCLASS_OF_CLASS_LABELS)


def rule_like_class_labels_preview() -> str:
    """Return rule-like class labels as backticked prompt text."""
    return format_backticked_or_list(tuple(sorted(RULE_LIKE_CLASS_LABELS)))


def declarative_source_class_labels_preview() -> str:
    """Return declarative source-like class labels as backticked prompt text."""
    return format_backticked_or_list(tuple(sorted(DECLARATIVE_SOURCE_CLASS_LABELS)))


def actor_class_labels() -> Tuple[str, ...]:
    """Return actor-like class labels used by non-prompt backend helpers."""
    return ("Social Agent", "Human", "Organisation")


def broad_placeholder_class_labels() -> Tuple[str, ...]:
    """Return broad placeholder class labels used by validation helpers."""
    return ("Organisation", "Social Agent", "Human", "Object", "Behaviour")


def preferred_source_property_label(
    subject_class_labels: set[str],
    source_class_labels: set[str],
) -> str:
    """Choose the preferred source-link property label for a subject/source pair."""
    if (
        subject_class_labels.intersection(RULE_LIKE_CLASS_LABELS)
        and source_class_labels.intersection(DECLARATIVE_SOURCE_CLASS_LABELS)
    ):
        return DECLARED_BY_LABEL
    return DESCRIBED_BY_LABEL


def creation_context_property_label() -> str:
    """Return the ontology label used for export creation-context statements."""
    return CREATION_CONTEXT_PROPERTY_LABEL


def creation_context_value_prefix() -> str:
    """Return the text prefix used for export creation-context statement values."""
    return CREATION_CONTEXT_VALUE_PREFIX


def is_new_item_placeholder(value: Any) -> bool:
    """Return whether a value is a configured new-item placeholder token."""
    return isinstance(value, str) and value.startswith(NEW_ITEM_PLACEHOLDER_PREFIX)


def new_item_placeholder(index: int) -> str:
    """Return the configured placeholder token for a new item index."""
    return f"{NEW_ITEM_PLACEHOLDER_PREFIX}{NEW_ITEM_PLACEHOLDER_STEM}_{index}"


def required_modeling_row_warning(subject_label: str) -> str:
    """Return the configured warning for a missing new-item modeling row."""
    return (
        f'New item "{subject_label}" is missing a required model row '
        f"({model_construct_property_labels_preview()})."
    )


def conflicting_modeling_row_warning(subject_label: str) -> str:
    """Return the configured warning for conflicting new-item modeling rows."""
    return (
        f'New item "{subject_label}" has both instance-style '
        f"({instance_of_class_labels_preview()}) and subclass-style "
        f"({subclass_of_class_labels_preview()}) model rows; review which one should remain."
    )


def property_id_from_entity(value: Any) -> Optional[str]:
    """Extract a bare property id from an ontology entity string.

    Args:
        value: Candidate property URI or id.

    Returns:
        A normalized `P...` id when present.
    """
    if not isinstance(value, str):
        return None
    text = value.strip().rstrip("/")
    if not text:
        return None
    tail = text.rsplit("/", 1)[-1]
    if tail.upper().startswith("P") and tail[1:].isdigit():
        return tail.upper()
    return None


def _normalized_label(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).casefold().split())


def _shape_config_values(values: Any, key: str) -> Iterable[str]:
    if isinstance(values, dict):
        raw = values.get(key)
        if isinstance(raw, str) and raw.strip():
            yield raw.strip()
        for value in values.values():
            yield from _shape_config_values(value, key)
    elif isinstance(values, list):
        for value in values:
            yield from _shape_config_values(value, key)


def _configured_property_labels() -> Tuple[str, ...]:
    labels: List[str] = []
    for group in (
        CONTEXT_MODEL_CONSTRUCT_PROPERTY_LABELS,
        CLASSIFICATION_PROPERTY_LABELS,
        MODEL_CONSTRUCT_PROPERTY_LABELS,
        INSTANCE_OF_CLASS_LABELS,
        SUBCLASS_OF_CLASS_LABELS,
        SOURCE_PROPERTY_LABELS,
        REFERENCE_PROPERTY_LABELS,
        (CREATION_CONTEXT_PROPERTY_LABEL,),
    ):
        for label in group:
            if label and label not in labels:
                labels.append(label)
    for label in _shape_config_values(SHAPE_DEFINITIONS, "propertyLabel"):
        if label and label not in labels:
            labels.append(label)
    return tuple(labels)


def _configured_item_labels() -> Tuple[str, ...]:
    labels: List[str] = []
    for group in (
        SOURCE_LIKE_MODEL_CONSTRUCT_LABELS,
        tuple(SOURCE_LIKE_MODEL_CONSTRUCT_PRIORITY),
        actor_class_labels(),
        tuple(RULE_LIKE_CLASS_LABELS),
        tuple(DECLARATIVE_SOURCE_CLASS_LABELS),
        tuple(DESCRIPTIVE_SOURCE_CLASS_LABELS),
        broad_placeholder_class_labels(),
    ):
        for label in group:
            if label and label not in labels:
                labels.append(label)
    for allowed_labels in REFERENCE_ALLOWED_CLASS_LABELS.values():
        for label in allowed_labels:
            if label and label not in labels:
                labels.append(label)
    return tuple(labels)


def validate_ontology_config(ontology_index: Dict[str, Any]) -> List[str]:
    """Validate configured ontology policy against a loaded ontology index.

    Args:
        ontology_index: Loaded ontology lookup index.

    Returns:
        Human-readable validation errors. An empty list means the config is aligned.
    """
    errors: List[str] = []
    by_entity = ontology_index.get("by_entity", {})
    property_labels = ontology_index.get("property_labels", {})
    label_to_entities = ontology_index.get("label_to_entities", {})

    if not MODEL_CONSTRUCT_PROPERTY_LABELS:
        errors.append("MODEL_CONSTRUCT_PROPERTY_LABELS must contain at least one configured property label.")
    if not INSTANCE_OF_CLASS_LABELS:
        errors.append("INSTANCE_OF_CLASS_LABELS must contain at least one configured property label.")
    if not SUBCLASS_OF_CLASS_LABELS:
        errors.append("SUBCLASS_OF_CLASS_LABELS must contain at least one configured property label.")
    if not SOURCE_PROPERTY_LABELS:
        errors.append("SOURCE_PROPERTY_LABELS must contain at least one configured property label.")
    if not REFERENCE_PROPERTY_LABELS:
        errors.append("REFERENCE_PROPERTY_LABELS must contain at least one configured property label.")

    reference_label_set = set(REFERENCE_PROPERTY_LABELS)
    for label in REFERENCE_PROPERTY_LABELS:
        if label not in REFERENCE_ALLOWED_CLASS_LABELS:
            errors.append(f"REFERENCE_ALLOWED_CLASS_LABELS is missing policy for reference property label: {label!r}.")
    for label in REFERENCE_ALLOWED_CLASS_LABELS:
        if label not in reference_label_set:
            errors.append(f"REFERENCE_ALLOWED_CLASS_LABELS contains a label not listed in REFERENCE_PROPERTY_LABELS: {label!r}.")

    for label in _configured_property_labels():
        if _normalized_label(label) not in property_labels:
            errors.append(f"Configured property label is missing from ontology.json: {label!r}.")

    for label in _configured_item_labels():
        if _normalized_label(label) not in label_to_entities:
            errors.append(f"Configured item/class label is missing from ontology.json: {label!r}.")

    for uri in _shape_config_values(SHAPE_DEFINITIONS, "property"):
        row = by_entity.get(uri)
        if not row:
            errors.append(f"Configured shape property URI is missing from ontology.json: {uri!r}.")
        elif row.get("entityType") != "property":
            errors.append(f"Configured shape property URI is not a property in ontology.json: {uri!r}.")

    for uri in _shape_config_values(SHAPE_DEFINITIONS, "entity"):
        if uri not in by_entity:
            errors.append(f"Configured shape entity URI is missing from ontology.json: {uri!r}.")

    return errors


def disallowed_extractor_properties(ontology_index: Dict[str, Any]) -> List[Dict[str, str]]:
    """List blocked ontology properties for extractor output.

    Args:
        ontology_index: Loaded ontology lookup index.

    Returns:
        Blocked property metadata for prompt payloads.
    """
    rows: List[Dict[str, str]] = []
    seen: set[str] = set()
    for row in ontology_index.get("properties", []):
        if not isinstance(row, dict):
            continue
        property_id = property_id_from_entity(row.get("entity"))
        if property_id not in DISALLOWED_EXTRACTOR_PROPERTY_IDS or property_id in seen:
            continue
        seen.add(property_id)
        rows.append({
            "entity": str(row.get("entity") or property_id),
            "property_id": property_id,
            "entityLabel": str(row.get("entityLabel") or property_id),
        })

    for property_id in DISALLOWED_EXTRACTOR_PROPERTY_IDS:
        if property_id in seen:
            continue
        rows.append({
            "entity": property_id,
            "property_id": property_id,
            "entityLabel": property_id,
        })
    return rows
