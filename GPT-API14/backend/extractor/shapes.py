"""Structured shape constraints used as modeling guidance for extraction."""

from typing import Any, Dict, List, Optional

ENTITY_BASE_URI = "https://organisational-rules.wikibase.cloud/entity/"

def _entity_uri(entity_id: str) -> str:
    return f"{ENTITY_BASE_URI}{entity_id}"

def _cardinality(min_count: int, max_count: Optional[int] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"min": min_count}
    if max_count is not None:
        out["max"] = max_count
    return out

SHAPE_CONSTRAINTS_NOTE = (
    "These shapes are extra modeling guidance derived from the ontology. Apply them when they "
    "fit a subject you create or edit, but do not treat unchanged existing KB rows as invalid "
    "just because they are outside these shapes."
)

SHAPE_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "DeclarativeRuleDescription",
        "target": {
            "property": _entity_uri("P1"),
            "propertyLabel": "instance of Class",
            "allowedValues": [
                {
                    "entity": _entity_uri("Q9"),
                    "label": "Declarative Rule Description",
                },
            ],
            "cardinality": _cardinality(1, 1),
        },
        "requirements": [
            {
                "property": _entity_uri("P1"),
                "propertyLabel": "instance of Class",
                "valueKind": "entity",
                "allowedValues": [
                    {
                        "entity": _entity_uri("Q9"),
                        "label": "Declarative Rule Description",
                    },
                ],
                "cardinality": _cardinality(1, 1),
            },
            {
                "property": _entity_uri("P7"),
                "propertyLabel": "official title",
                "valueKind": "literal",
                "cardinality": _cardinality(1),
            },
            {
                "property": _entity_uri("P9"),
                "propertyLabel": "web page URL",
                "valueKind": "iri",
                "cardinality": _cardinality(1, 1),
            },
            {
                "property": _entity_uri("P16"),
                "propertyLabel": "complies to",
                "valueKind": "entity",
                "objectShape": "DeclarativeRuleDescription",
                "cardinality": _cardinality(0),
            },
            {
                "property": _entity_uri("P73"),
                "propertyLabel": "instance of",
                "valueKind": "entity",
                "objectShape": "DeclarativeRuleDescription",
                "cardinality": _cardinality(0),
            },
        ],
    },
    {
        "name": "NonStructuralRule",
        "target": {
            "property": _entity_uri("P1"),
            "propertyLabel": "instance of Class",
            "allowedValues": [
                {
                    "entity": _entity_uri("Q52"),
                    "label": "Operational Rule",
                },
                {
                    "entity": _entity_uri("Q340"),
                    "label": "Goal",
                },
            ],
            "cardinality": _cardinality(1, 1),
        },
        "requirements": [
            {
                "property": _entity_uri("P1"),
                "propertyLabel": "instance of Class",
                "valueKind": "entity",
                "allowedValues": [
                    {
                        "entity": _entity_uri("Q52"),
                        "label": "Operational Rule",
                    },
                    {
                        "entity": _entity_uri("Q340"),
                        "label": "Goal",
                    },
                ],
                "cardinality": _cardinality(1, 1),
            },
            {
                "kind": "any_of_properties",
                "properties": [
                    {
                        "entity": _entity_uri("P3"),
                        "label": "constrains (inverse of constrained by)",
                    },
                    {
                        "entity": _entity_uri("P40"),
                        "label": "prohibits (inverse of prohibited by)",
                    },
                    {
                        "entity": _entity_uri("P83"),
                        "label": "allows (inverse of allowed by)",
                    },
                    {
                        "entity": _entity_uri("P56"),
                        "label": "demands (inverse of demanded by)",
                    },
                    {
                        "entity": _entity_uri("P85"),
                        "label": "controls (inverse of controlled by)",
                    },
                    {
                        "entity": _entity_uri("P99"),
                        "label": "constrains - enables",
                    },
                ],
                "valueKind": "entity_or_literal",
                "cardinality": _cardinality(1),
            },
        ],
    },
]

def compact_shapes_for_prompt() -> List[Dict[str, Any]]:
    return [
        {
            "name": shape["name"],
            "target": shape["target"],
            "requirements": shape["requirements"],
        }
        for shape in SHAPE_DEFINITIONS
    ]