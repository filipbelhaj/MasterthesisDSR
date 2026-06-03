"""Ontology loading and statement-row normalization helpers for extractor outputs."""

import re
from typing import Any, Dict, List, Optional
from ..state import norm

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
REFERENCE_ENTRY_FIELDS = (
    "property",
    "propertyLabel",
    "value",
    "valueLabel",
)

ACCIDENTAL_QUOTE_ESCAPE_RE = re.compile(r'(?<!\\)\\(["\'])')

def empty_ontology_index() -> Dict[str, Any]:
    """Build an empty ontology index structure.

    Returns:
        A blank ontology index with the expected keys.
    """
    return {
        "raw": [],
        "by_entity": {},
        "items": [],
        "properties": [],
        "label_to_entities": {},
        "property_labels": {},
        "property_id_to_label": {},
    }

def _extract_property_id(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip().rstrip("/")
    if not text:
        return None
    tail = text.rsplit("/", 1)[-1]
    if tail.upper().startswith("P") and tail[1:].isdigit():
        return tail.upper()
    return None

def _compact_entities(rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    return [{
        "entity": row.get("entity"),
        "entityLabel": row.get("entityLabel"),
        "entityDescription": row.get("entityDescription"),
    } for row in rows[:limit]]

class OntologyStore:
    """Hold the loaded ontology rows, lookup indexes, and prompt cache."""

    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []
        self.index: Dict[str, Any] = empty_ontology_index()
        self.compact_prompt_cache: Dict[str, Any] = {"properties": [], "items": []}
        self.load_error: Optional[str] = None

    def build_index(self, ontology_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build lookup tables from ontology export rows.

        Args:
            ontology_rows: Raw ontology rows from JSON.

        Returns:
            Indexes used for validation, lookup, and prompt context.
        """
        # This index is shared by validation, label lookup, and the compact ontology
        # snapshot we pass into prompts, so we build it once when the file loads.
        by_entity: Dict[str, Dict[str, Any]] = {}
        items: List[Dict[str, Any]] = []
        properties: List[Dict[str, Any]] = []
        label_to_entities: Dict[str, List[str]] = {}
        property_labels: Dict[str, str] = {}
        property_id_to_label: Dict[str, str] = {}

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
                    property_id = _extract_property_id(entity)
                    if property_id:
                        property_id_to_label[property_id] = label
                alt_label = row.get("entityAltLabel")
                if alt_label and entity:
                    property_labels.setdefault(norm(alt_label), entity)

        return {
            "raw": ontology_rows,
            "by_entity": by_entity,
            "items": items,
            "properties": properties,
            "label_to_entities": label_to_entities,
            "property_labels": property_labels,
            "property_id_to_label": property_id_to_label,
        }

    def load(self, ontology_rows: List[Dict[str, Any]]) -> None:
        """Load ontology rows and refresh cached indexes.

        Args:
            ontology_rows: Raw ontology rows from JSON.

        Returns:
            None.
        """
        self.rows = ontology_rows
        self.index = self.build_index(ontology_rows)
        self.compact_prompt_cache = {
            "properties": _compact_entities(self.index["properties"], 1000),
            "items": _compact_entities(self.index["items"], 800),
        }
        self.load_error = None

ONTOLOGY = OntologyStore()

def is_valid_property_uri(uri: Optional[str]) -> bool:
    """Check whether a URI belongs to an ontology property.

    Args:
        uri: Candidate ontology entity URI.

    Returns:
        True when the URI resolves to a property row.
    """
    if not uri:
        return False
    row = ONTOLOGY.index["by_entity"].get(uri)
    return bool(row and row.get("entityType") == "property")

def _canonical_property_label(value: Any) -> Optional[str]:
    if value is None:
        return None

    # Extractors and manual edits may refer to a property by full URI or bare P-id;
    # normalize both back to the ontology label so downstream output stays consistent.
    row = ONTOLOGY.index["by_entity"].get(value)
    if row and row.get("entityType") == "property":
        label = row.get("entityLabel")
        return str(label).strip() if isinstance(label, str) and label.strip() else None

    property_id = _extract_property_id(value)
    if not property_id:
        return None

    label = ONTOLOGY.index["property_id_to_label"].get(property_id)
    return str(label).strip() if isinstance(label, str) and label.strip() else None

def _canonicalize_property_labels(row: Dict[str, Any]) -> Dict[str, Any]:
    canonical_property = _canonical_property_label(row.get("property"))
    if canonical_property:
        row["propertyLabel"] = canonical_property

    canonical_qualifier = _canonical_property_label(row.get("qualifierProperty"))
    if canonical_qualifier:
        row["qualifierPropertyLabel"] = canonical_qualifier

    return row

def _normalize_text_escapes(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    # Some model outputs leak JSON-style escaping into the actual field content,
    # e.g. \"risk\" instead of "risk". Collapse only those simple quote escapes.
    return ACCIDENTAL_QUOTE_ESCAPE_RE.sub(r"\1", value)

def normalize_statement_strings(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize escaped string content within a statement row.

    Args:
        row: Statement row to normalize.

    Returns:
        A row copy with cleaned string values and references.
    """
    normalized: Dict[str, Any] = {}
    for key, value in row.items():
        if key == "references" and isinstance(value, list):
            normalized[key] = [
                {
                    ref_key: _normalize_text_escapes(ref_value)
                    for ref_key, ref_value in reference.items()
                }
                for reference in value
                if isinstance(reference, dict)
            ]
            continue
        normalized[key] = _normalize_text_escapes(value)
    return normalized

def clean_reference_entry(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Validate and normalize one reference entry.

    Args:
        entry: Raw reference object from model or user input.

    Returns:
        A cleaned reference entry, or `None` when invalid.
    """
    if entry.get("property") is None or entry.get("value") is None:
        return None
    if not is_valid_property_uri(entry.get("property")):
        return None
    cleaned = normalize_statement_strings({
        key: value for key, value in ((field, entry.get(field)) for field in REFERENCE_ENTRY_FIELDS) if value is not None
    })
    return _canonicalize_property_labels(cleaned)

def clean_statement_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Validate and normalize one statement row.

    Args:
        row: Raw statement row from model or user input.

    Returns:
        A cleaned statement row, or `None` when invalid.
    """
    # Keep the validation gate intentionally small: require the core triple and a
    # known property, but preserve any optional labels or qualifiers already resolved.
    if row.get("item") is None or row.get("property") is None or row.get("value") is None:
        return None
    if not is_valid_property_uri(row.get("property")):
        return None
    cleaned = normalize_statement_strings({
        key: value for key, value in ((field, row.get(field)) for field in STATEMENT_FIELDS) if value is not None
    })
    return _canonicalize_property_labels(cleaned)

def compact_ontology_for_prompt() -> Dict[str, Any]:
    """Return the cached ontology summary used in prompts.

    Returns:
        The compact ontology payload for extractor prompts.
    """
    return ONTOLOGY.compact_prompt_cache
