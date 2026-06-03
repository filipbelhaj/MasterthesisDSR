"""User-editable ontology profile.

Edit this file when pairing the application with a different ontology while
keeping the rest of the extraction pipeline unchanged.

When changing ontology:
1. Set ENTITY_BASE_URI to your Wikibase entity namespace.
2. Update modeling/classification property labels.
3. Update source/reference property labels and class policies.
4. Update source-like and rule-like class labels.
5. Update prioritized concept labels.
6. Set disallowed property IDs, or leave the tuple empty.
7. Update SHAPE_DEFINITIONS after Wikibase has assigned the needed Q/P IDs, or
   leave it empty if no extra shape guidance is needed.
8. Upload ontology.json and fix any validation messages.
"""

from typing import Any, Dict, List


# Property IDs that exist in the ontology but should never be used by extractor
# output. These are bare Wikibase property IDs, not full entity URIs.
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


# Properties used to identify the class/type of entities in the existing KB
# context and in new extractor-created items.
CONTEXT_MODEL_CONSTRUCT_PROPERTY_LABELS = (
    "instance of Class",
    "subclass of Class",
)

CLASSIFICATION_PROPERTY_LABELS = ("instance of Class", "subclass of Class")

MODEL_CONSTRUCT_PROPERTY_LABELS = (
    "instance of Class",
    "subclass of Class",
)

INSTANCE_OF_CLASS_LABELS = ("instance of Class",)
SUBCLASS_OF_CLASS_LABELS = ("subclass of Class",)


# Classes that represent source documents, sections, or descriptions. These are
# used to detect source candidates in the existing KB.
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


# Source-link and reference properties.
DESCRIBED_BY_LABEL = "described by"
DECLARED_BY_LABEL = "declared by"
DEFINED_BY_LABEL = "defined by"
SOURCE_PROPERTY_LABELS = (DESCRIBED_BY_LABEL, DECLARED_BY_LABEL)
REFERENCE_PROPERTY_LABELS = (DESCRIBED_BY_LABEL, DECLARED_BY_LABEL, DEFINED_BY_LABEL)


# Classes and source policies used to choose source-link properties and validate
# structured references.
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
    DEFINED_BY_LABEL: {"Structural Rule", "Organisational Rule", "Declarative Rule Description"},
    DECLARED_BY_LABEL: {"Operational Rule", "Organisational Rule"} | DECLARATIVE_SOURCE_CLASS_LABELS,
    DESCRIBED_BY_LABEL: DESCRIPTIVE_SOURCE_CLASS_LABELS,
}


# Concept labels surfaced in the prompt as extraction priorities.
PRIORITIZED_CONCEPT_LABELS = {
    "agent": "Agent",
    "rule": "Organisational Rule",
    "declarative_source": "Declarative Rule Description",
    "action_object": "Action / Object",
    "assessment": "Assessment",
}


# Wikibase entity namespace and QuickStatements creation metadata.
ENTITY_BASE_URI = "https://organisational-rules.wikibase.cloud/entity/"
CREATION_CONTEXT_PROPERTY_LABEL = "creation context"
CREATION_CONTEXT_VALUE_PREFIX = "semi-automatic: ORS Explorer"


# Optional shape constraints passed to the extractor as extra modeling guidance.
# For a new ontology, it is safe to start with SHAPE_DEFINITIONS = [] and add
# shapes later after the needed Wikibase Q/P IDs are known.
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
