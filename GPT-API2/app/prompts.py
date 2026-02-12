from __future__ import annotations
def extraction_instructions() -> str:
    return (
        "You update a statement KB (Wikibase-like rows).\n"
        "Return ONLY JSON matching the schema.\n\n"
        "Rules:\n"
        "- Propose ONLY additions strongly supported by SECTION.\n"
        "- Reuse URIs from KB_CONTEXT when relevant.\n"
        "- If a new entity is needed, use:\n"
        "  https://organisational-rules.wikibase.cloud/entity/QNEW_<slug>\n"
        "  with a short lowercase slug using letters/digits/underscores.\n"
        "- Every addition MUST include correct labels (itemLabel/propertyLabel/valueLabel).\n"
        "- Provide a VERY short reason per addition (max ~25 words), aligned by index.\n"
    )

def kb_additions_schema() -> dict:
    # JSON schema for OpenAI response_format=json_schema
    return {
        "name": "kb_additions_with_reasons",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["additions", "reasons"],
            "properties": {
                "additions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "item": {"type": "string"},
                            "itemLabel": {"type": "string"},
                            "property": {"type": "string"},
                            "propertyLabel": {"type": "string"},
                            "value": {"type": "string"},
                            "valueLabel": {"type": "string"},
                            "qualifierProperty": {"type": ["string", "null"]},
                            "qualifierValue": {"type": ["string", "null"]},
                            "qualifierPropertyLabel": {"type": ["string", "null"]},
                            "qualifierValueLabel": {"type": ["string", "null"]},
                        },
                        "required": [
                            "item",
                            "itemLabel",
                            "property",
                            "propertyLabel",
                            "value",
                            "valueLabel",
                            "qualifierProperty",
                            "qualifierValue",
                            "qualifierPropertyLabel",
                            "qualifierValueLabel",
                        ],
                    },
                },
                "reasons": {"type": "array", "items": {"type": "string"}},
            },
        },
    }
