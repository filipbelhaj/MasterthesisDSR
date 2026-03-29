"""Ontology loading and statement-row normalization helpers for extractor outputs."""

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

def empty_ontology_index() -> Dict[str, Any]:
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
    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []
        self.index: Dict[str, Any] = empty_ontology_index()
        self.compact_prompt_cache: Dict[str, Any] = {"properties": [], "items": []}
        self.load_error: Optional[str] = None

    def build_index(self, ontology_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
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

def clean_statement_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # Keep the validation gate intentionally small: require the core triple and a
    # known property, but preserve any optional labels or qualifiers already resolved.
    if row.get("item") is None or row.get("property") is None or row.get("value") is None:
        return None
    if not is_valid_property_uri(row.get("property")):
        return None
    cleaned = {key: value for key, value in ((field, row.get(field)) for field in STATEMENT_FIELDS) if value is not None}
    return _canonicalize_property_labels(cleaned)

def compact_ontology_for_prompt() -> Dict[str, Any]:
    return ONTOLOGY.compact_prompt_cache
