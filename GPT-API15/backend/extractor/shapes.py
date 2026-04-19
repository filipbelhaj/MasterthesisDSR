"""Structured shape constraints used as modeling guidance for extraction."""

from typing import Any, Dict, List

from .ontology_rules import SHAPE_CONSTRAINTS_NOTE, SHAPE_DEFINITIONS

def compact_shapes_for_prompt() -> List[Dict[str, Any]]:
    return [
        {
            "name": shape["name"],
            "target": shape["target"],
            "requirements": shape["requirements"],
        }
        for shape in SHAPE_DEFINITIONS
    ]
