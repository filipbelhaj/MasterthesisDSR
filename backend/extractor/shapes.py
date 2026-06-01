"""Structured shape constraints used as modeling guidance for extraction."""

from typing import Any, Dict, List

from ..core.ontology_config import SHAPE_DEFINITIONS

def compact_shapes_for_prompt() -> List[Dict[str, Any]]:
    """Return the shape subset passed into extractor prompts.

    Returns:
        Compact shape definitions for prompt guidance.
    """
    return [
        {
            "name": shape["name"],
            "target": shape["target"],
            "requirements": shape["requirements"],
        }
        for shape in SHAPE_DEFINITIONS
    ]
