import json
from pathlib import Path

# Each row is a dict from JSON
def load_kb(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"KB file not found at {path}. Expected query.json next to api.py.")
    kb = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(kb, list):
        raise ValueError("query.json must be a list of objects")
    return kb


def row_key(r: dict) -> tuple[str, str, str, str, str]:
    """Dedup key for a KB row (including optional qualifier)."""
    keys = ("item", "property", "value", "qualifierProperty", "qualifierValue")
    return tuple((r.get(k) or "") for k in keys)


def build_label_maps(kb) -> tuple[dict, dict, dict]:
    """Build canonical label maps from existing KB rows."""
    item_label, prop_label, value_label = {}, {}, {}
    for r in kb:
        if r.get("item") and r.get("itemLabel"):
            item_label[r["item"]] = r["itemLabel"]
        if r.get("property") and r.get("propertyLabel"):
            prop_label[r["property"]] = r["propertyLabel"]
        if r.get("value") and r.get("valueLabel"):
            value_label[r["value"]] = r["valueLabel"]
    return item_label, prop_label, value_label


def fix_labels(add: dict, item_label: dict, prop_label: dict, value_label: dict) -> dict:
    """For URIs already in KB, force canonical labels from KB."""
    def set_label(uri_key: str, label_key: str, mapping: dict):
        uri = add.get(uri_key)
        if uri in mapping:
            add[label_key] = mapping[uri]

    set_label("item", "itemLabel", item_label)
    set_label("property", "propertyLabel", prop_label)
    set_label("value", "valueLabel", value_label)
    set_label("qualifierProperty", "qualifierPropertyLabel", prop_label)
    set_label("qualifierValue", "qualifierValueLabel", value_label)
    return add

