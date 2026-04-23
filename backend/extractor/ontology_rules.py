"""Centralized ontology-specific extractor policy.

Edit this module when pairing the extractor with a different ontology while
keeping the rest of the extraction pipeline unchanged.
"""

from typing import Any, Dict, List, Optional, Tuple


DISALLOWED_EXTRACTOR_PROPERTY_IDS = (
    "P17",
    "P47",
    "P48",
    "P49",
    "P50",
    "P52",
    "P53",
    "P55",
    "P57",
    "P58",
    "P75",
    "P78",
    "P82",
    "P109",
    "P112",
    "P113",
    "P118",
    "P124",
    "P125",
    "P126",
    "P127",
    "P129",
    "P132",
    "P136",
    "P137",
    "P138",
    "P139",
    "P140",
    "P141",
    "P144",
)

DISALLOWED_EXTRACTOR_PROPERTY_NOTE = (
    "These ontology properties exist in the KB but are blocked for extractor output because "
    "they are often misunderstood, too meta-level, or lower-value for this workflow. "
    "Do not use them in `property` or `qualifierProperty`."
)

CONTEXT_MODEL_CONSTRUCT_PROPERTY_LABELS = (
    "particular of model construct",
    "universal of model construct",
)

SOURCE_LIKE_MODEL_CONSTRUCT_LABELS = (
    "Declarative Rule Description",
    "Rule Description",
    "Description Section",
    "Description Collection",
    "Description",
    "Self-contained Description",
)

SOURCE_LIKE_MODEL_CONSTRUCT_PRIORITY = {
    "Description Section": 0,
    "Declarative Rule Description": 1,
    "Rule Description": 1,
    "Description Collection": 2,
    "Description": 3,
    "Self-contained Description": 4,
}

ACTOR_CLASS_LABELS = ("Social Agent", "Human", "Organisation")
CLASSIFICATION_PROPERTY_LABELS = ("instance of Class", "subclass of Class")

MODEL_CONSTRUCT_PROPERTY_LABELS = (
    "instance of Class",
    "subclass of Class",
    "particular of model construct",
    "universal of model construct",
)

INSTANCE_OF_CLASS_LABELS = ("instance of Class", "particular of model construct")
SUBCLASS_OF_CLASS_LABELS = ("subclass of Class", "universal of model construct")

SOURCE_PROPERTY_LABELS = ("described by", "declared by")
REFERENCE_PROPERTY_LABELS = ("described by", "declared by", "defined by")

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

DESCRIPTIVE_SOURCE_CLASS_LABELS = {
    "Description",
    "Rule Description",
    "Declarative Rule Description",
    "Description Section",
    "Description Collection",
    "Self-contained Description",
}

REFERENCE_ALLOWED_CLASS_LABELS = {
    "defined by": {"Structural Rule", "Organisational Rule", "Declarative Rule Description"},
    "declared by": {"Operational Rule", "Organisational Rule", "Declarative Rule Description"},
    "described by": DESCRIPTIVE_SOURCE_CLASS_LABELS,
}

BROAD_PLACEHOLDER_CLASS_LABELS = (
    "Organisation",
    "Social Agent",
    "Human",
    "Object",
    "Behaviour",
)

PRIORITIZED_CONCEPT_LABELS = {
    "agent": "Agent",
    "rule": "Organisational Rule",
    "declarative_source": "Declarative Rule Description",
    "action_object": "Action / Object",
    "assessment": "Assessment",
}

ENTITY_BASE_URI = "https://organisational-rules.wikibase.cloud/entity/"

SHAPE_CONSTRAINTS_NOTE = (
    "These shapes are extra modeling guidance derived from the ontology. Apply them when they "
    "fit a subject you create or edit, but do not treat unchanged existing KB rows as invalid "
    "just because they are outside these shapes."
)

SHAPE_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "DeclarativeRuleDescription",
        "target": {
            "property": f"{ENTITY_BASE_URI}P1",
            "propertyLabel": "instance of Class",
            "allowedValues": [
                {
                    "entity": f"{ENTITY_BASE_URI}Q9",
                    "label": "Declarative Rule Description",
                },
            ],
            "cardinality": {"min": 1, "max": 1},
        },
        "requirements": [
            {
                "property": f"{ENTITY_BASE_URI}P1",
                "propertyLabel": "instance of Class",
                "valueKind": "entity",
                "allowedValues": [
                    {
                        "entity": f"{ENTITY_BASE_URI}Q9",
                        "label": "Declarative Rule Description",
                    },
                ],
                "cardinality": {"min": 1, "max": 1},
            },
            {
                "property": f"{ENTITY_BASE_URI}P7",
                "propertyLabel": "official title",
                "valueKind": "literal",
                "cardinality": {"min": 1},
            },
            {
                "property": f"{ENTITY_BASE_URI}P9",
                "propertyLabel": "web page URL",
                "valueKind": "iri",
                "cardinality": {"min": 1, "max": 1},
            },
            {
                "property": f"{ENTITY_BASE_URI}P16",
                "propertyLabel": "complies to",
                "valueKind": "entity",
                "objectShape": "DeclarativeRuleDescription",
                "cardinality": {"min": 0},
            },
            {
                "property": f"{ENTITY_BASE_URI}P73",
                "propertyLabel": "instance of",
                "valueKind": "entity",
                "objectShape": "DeclarativeRuleDescription",
                "cardinality": {"min": 0},
            },
        ],
    },
    {
        "name": "NonStructuralRule",
        "target": {
            "property": f"{ENTITY_BASE_URI}P1",
            "propertyLabel": "instance of Class",
            "allowedValues": [
                {
                    "entity": f"{ENTITY_BASE_URI}Q52",
                    "label": "Operational Rule",
                },
                {
                    "entity": f"{ENTITY_BASE_URI}Q340",
                    "label": "Goal",
                },
            ],
            "cardinality": {"min": 1, "max": 1},
        },
        "requirements": [
            {
                "property": f"{ENTITY_BASE_URI}P1",
                "propertyLabel": "instance of Class",
                "valueKind": "entity",
                "allowedValues": [
                    {
                        "entity": f"{ENTITY_BASE_URI}Q52",
                        "label": "Operational Rule",
                    },
                    {
                        "entity": f"{ENTITY_BASE_URI}Q340",
                        "label": "Goal",
                    },
                ],
                "cardinality": {"min": 1, "max": 1},
            },
            {
                "kind": "any_of_properties",
                "properties": [
                    {
                        "entity": f"{ENTITY_BASE_URI}P3",
                        "label": "constrains (inverse of constrained by)",
                    },
                    {
                        "entity": f"{ENTITY_BASE_URI}P40",
                        "label": "prohibits (inverse of prohibited by)",
                    },
                    {
                        "entity": f"{ENTITY_BASE_URI}P83",
                        "label": "allows (inverse of allowed by)",
                    },
                    {
                        "entity": f"{ENTITY_BASE_URI}P56",
                        "label": "demands (inverse of demanded by)",
                    },
                    {
                        "entity": f"{ENTITY_BASE_URI}P85",
                        "label": "controls (inverse of controlled by)",
                    },
                    {
                        "entity": f"{ENTITY_BASE_URI}P99",
                        "label": "constrains - enables",
                    },
                ],
                "valueKind": "entity_or_literal",
                "cardinality": {"min": 1},
            },
        ],
    },
]


def format_backticked_or_list(labels: Tuple[str, ...]) -> str:
    quoted = [f"`{label}`" for label in labels]
    if not quoted:
        return ""
    if len(quoted) == 1:
        return quoted[0]
    if len(quoted) == 2:
        return f"{quoted[0]} or {quoted[1]}"
    return ", ".join(quoted[:-1]) + f", or {quoted[-1]}"


def format_plain_or_list(labels: Tuple[str, ...]) -> str:
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} or {labels[1]}"
    return ", ".join(labels[:-1]) + f", or {labels[-1]}"


def property_id_from_entity(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip().rstrip("/")
    if not text:
        return None
    tail = text.rsplit("/", 1)[-1]
    if tail.upper().startswith("P") and tail[1:].isdigit():
        return tail.upper()
    return None


def disallowed_extractor_properties(ontology_index: Dict[str, Any]) -> List[Dict[str, str]]:
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
