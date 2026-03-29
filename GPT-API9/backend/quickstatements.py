"""Conversion utilities for turning approved rows into Wikibase QuickStatements output."""

from __future__ import annotations
import re
from typing import Any, Iterable
from urllib.parse import urlparse
from .state import canonical_row_key

PLACEHOLDER_PREFIXES = ("QNEW", "NEW:")
PLACEHOLDER_LABEL_FIELDS = (
    ("item", "itemLabel"),
    ("value", "valueLabel"),
    ("qualifierValue", "qualifierValueLabel"),
)
PLACEHOLDER_VALUE_FIELDS = ("item", "value", "qualifierValue")
QUALIFIER_FIELDS = ("qualifierProperty", "qualifierPropertyLabel", "qualifierValue", "qualifierValueLabel")
QID_RE = re.compile(r"^Q\d+$")

def _normalize_entity_token(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.startswith(PLACEHOLDER_PREFIXES):
        return text
    if "://" not in text:
        return text
    path = urlparse(text).path.rstrip("/")
    tail = path.rsplit("/", 1)[-1] if path else ""
    if tail.startswith(("Q", "P")) and tail[1:].isdigit():
        return tail
    return text

def _escape_literal(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')

def _qs_term(token: str, placeholder_to_qs_target: dict[str, str]) -> str:
    token = _normalize_entity_token(token)
    if token.startswith(PLACEHOLDER_PREFIXES):
        return placeholder_to_qs_target.get(token, token)
    if token.startswith("Q"):
        return token
    return f'"{_escape_literal(token)}"'

def _is_placeholder(token: Any) -> bool:
    return isinstance(token, str) and token.startswith(PLACEHOLDER_PREFIXES)

def _normalize_qid(value: Any) -> str:
    token = _normalize_entity_token(value)
    token_upper = token.upper()
    return token_upper if QID_RE.fullmatch(token_upper) else ""

def _row_summary(row: dict[str, Any]) -> str:
    subject = str(row.get("itemLabel") or row.get("item") or "row").strip()
    prop = str(row.get("propertyLabel") or row.get("property") or "property").strip()
    return f"{subject} / {prop}"

def _iter_placeholder_entries(row: dict[str, Any]):
    for entity_key, label_key in PLACEHOLDER_LABEL_FIELDS:
        token = row.get(entity_key)
        if not _is_placeholder(token):
            continue
        placeholder = str(token)
        label = str(row.get(label_key) or "").strip() or placeholder
        yield placeholder, label

def _append_create_lines(lines: list[str], label: str, lang: str) -> None:
    lines.append("CREATE")
    if label:
        lines.append(f'LAST\tL{lang}\t"{_escape_literal(label)}"')

def _normalize_bindings(bindings: dict[str, str] | None) -> tuple[dict[str, str], list[str]]:
    normalized: dict[str, str] = {}
    warnings: list[str] = []
    for placeholder, qid in (bindings or {}).items():
        if not _is_placeholder(placeholder):
            continue
        normalized_qid = _normalize_qid(qid)
        if normalized_qid:
            normalized[placeholder] = normalized_qid
        elif str(qid or "").strip():
            warnings.append(f"Ignored invalid QID binding for {placeholder!r}: {qid!r}.")
    return normalized, warnings

def _clear_qualifier(candidate: dict[str, Any]) -> None:
    for key in QUALIFIER_FIELDS:
        candidate.pop(key, None)

def collect_placeholder_manifest(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, str]], list[str]]:
    manifest: list[dict[str, str]] = []
    warnings: list[str] = []
    seen: dict[str, str] = {}
    seen_conflicts: set[tuple[str, str, str]] = set()

    for row in rows:
        if not isinstance(row, dict):
            continue
        for placeholder, label in _iter_placeholder_entries(row):
            existing = seen.get(placeholder)
            if existing is None:
                seen[placeholder] = label
                manifest.append({"placeholder": placeholder, "label": label})
            elif existing != label:
                conflict = (placeholder, existing, label)
                if conflict not in seen_conflicts:
                    seen_conflicts.add(conflict)
                    warnings.append(
                        f"Placeholder {placeholder!r} has conflicting labels {existing!r} and {label!r}; using the first one in Step 1."
                    )

    return manifest, warnings

def placeholder_manifest_template(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, str]], list[str]]:
    manifest, warnings = collect_placeholder_manifest(rows)
    return [
        {"placeholder": entry["placeholder"], "label": entry["label"], "qid": ""}
        for entry in manifest
    ], warnings

def placeholder_create_quickstatements(rows: Iterable[dict[str, Any]], lang: str = "en") -> tuple[str, list[dict[str, str]], list[str]]:
    manifest, warnings = collect_placeholder_manifest(rows)
    lines: list[str] = []
    for entry in manifest:
        _append_create_lines(lines, entry["label"], lang)
    return "\n".join(lines), manifest, warnings

def apply_placeholder_bindings(
    rows: Iterable[dict[str, Any]],
    bindings: dict[str, str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        updated = dict(row)
        for field in PLACEHOLDER_VALUE_FIELDS:
            token = updated.get(field)
            if not _is_placeholder(token):
                continue
            replacement = bindings.get(str(token), "").strip()
            if replacement:
                updated[field] = replacement
        out.append(updated)

    return out

def sanitize_rows_for_quickstatements(
    rows: Iterable[dict[str, Any]],
    *,
    allow_subject_placeholders: bool = True,
) -> tuple[list[dict[str, Any]], list[str], dict[int, int | None]]:
    """
    Remove or downgrade rows that cannot be represented safely in Wikibase Cloud
    QuickStatements:
    - brand-new placeholder objects (`value = NEW:*`) are dropped
    - brand-new placeholder qualifier values are removed from the row
    """
    sanitized: list[dict[str, Any]] = []
    warnings: list[str] = []
    # index_map keeps a link back to the original row positions so the API can report
    # how many rows were skipped or collapsed after QuickStatements sanitization.
    index_map: dict[int, int | None] = {}
    key_to_index: dict[tuple[Any, ...], int] = {}

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            index_map[idx] = None
            continue

        candidate = dict(row)
        value = candidate.get("value")
        qualifier_value = candidate.get("qualifierValue")
        summary = _row_summary(candidate)

        if not allow_subject_placeholders and _is_placeholder(candidate.get("item")):
            item_label = candidate.get("itemLabel") or candidate.get("item")
            warnings.append(
                f"Dropped QuickStatements row for {summary}: subject {item_label!r} is still unresolved. Fill in its QID before generating Step 2."
            )
            index_map[idx] = None
            continue

        if _is_placeholder(value):
            value_label = candidate.get("valueLabel") or value
            warnings.append(
                f"Dropped QuickStatements row for {summary}: value {value_label!r} is a new placeholder and Wikibase Cloud QuickStatements cannot import new object items inline."
            )
            index_map[idx] = None
            continue

        if _is_placeholder(qualifier_value):
            qualifier_label = candidate.get("qualifierValueLabel") or qualifier_value
            warnings.append(
                f"Removed QuickStatements qualifier from {summary}: qualifier value {qualifier_label!r} is a new placeholder and cannot be imported inline."
            )
            _clear_qualifier(candidate)

        key = canonical_row_key(candidate)
        existing_index = key_to_index.get(key)
        if existing_index is None:
            existing_index = len(sanitized)
            key_to_index[key] = existing_index
            sanitized.append(candidate)
        index_map[idx] = existing_index

    return sanitized, warnings, index_map

def build_step2_quickstatements(
    rows: Iterable[dict[str, Any]],
    bindings: dict[str, str] | None = None,
    *,
    lang: str = "en",
) -> dict[str, Any]:
    normalized_bindings, binding_warnings = _normalize_bindings(bindings)
    bound_rows = apply_placeholder_bindings(rows, normalized_bindings)
    # Step 2 only works after placeholder subjects are rebound to real QIDs; any
    # rows still pointing at placeholders are skipped with warnings below.
    sanitized_rows, qs_warnings, row_index_map = sanitize_rows_for_quickstatements(
        bound_rows,
        allow_subject_placeholders=False,
    )
    qs_text = rows_to_quickstatements(sanitized_rows, lang=lang)
    unresolved = [
        entry for entry in placeholder_manifest_template(bound_rows)[0]
        if not normalized_bindings.get(entry["placeholder"])
    ]
    return {
        "quickstatements": qs_text,
        "warnings": binding_warnings + qs_warnings,
        "skipped_rows": sum(1 for mapped in row_index_map.values() if mapped is None),
        "unresolved_placeholders": unresolved,
    }

def _row_to_quickstatements_parts(
    row: dict[str, Any],
    *,
    qs_item: str,
    placeholder_to_qs_target: dict[str, str],
) -> list[str]:
    prop = _normalize_entity_token(row.get("property", ""))
    value = _normalize_entity_token(row.get("value", ""))
    if not (qs_item and prop and value and prop.startswith("P")):
        return []

    parts = [qs_item, prop, _qs_term(value, placeholder_to_qs_target)]
    qp = _normalize_entity_token(row.get("qualifierProperty", "") or "")
    qv = _normalize_entity_token(row.get("qualifierValue", "") or "")
    if qp and qv and qp.startswith("P"):
        parts.extend([qp, _qs_term(qv, placeholder_to_qs_target)])
    return parts

def _append_placeholder_subject_rows(
    lines: list[str],
    placeholder: str,
    rows: list[dict[str, Any]],
    *,
    lang: str,
) -> None:
    if not rows:
        return
    # Emit one CREATE/LAST block per placeholder subject so all of its statements land
    # on the same freshly created entity.
    _append_create_lines(lines, str(rows[0].get("itemLabel", "")).strip(), lang)
    placeholder_to_qs_target = {placeholder: "LAST"}
    for row in rows:
        parts = _row_to_quickstatements_parts(row, qs_item="LAST", placeholder_to_qs_target=placeholder_to_qs_target)
        if parts:
            lines.append("\t".join(parts))

def rows_to_quickstatements(rows: Iterable[dict[str, Any]], lang: str = "en") -> str:
    """Build importable QuickStatements from finalized rows."""
    lines: list[str] = []
    row_list = [row for row in rows if isinstance(row, dict)]
    placeholder_groups: dict[str, list[dict[str, Any]]] = {}
    emitted_placeholders: set[str] = set()

    # Group placeholder subjects up front so repeated rows reuse one CREATE block
    # instead of creating duplicate new items.
    for row in row_list:
        item = _normalize_entity_token(row.get("item", ""))
        if item.startswith(PLACEHOLDER_PREFIXES):
            placeholder_groups.setdefault(item, []).append(row)

    for row in row_list:
        item = _normalize_entity_token(row.get("item", ""))
        if not (item.startswith("Q") or item.startswith(PLACEHOLDER_PREFIXES)):
            continue

        if item.startswith(PLACEHOLDER_PREFIXES):
            if item in emitted_placeholders:
                continue
            emitted_placeholders.add(item)
            _append_placeholder_subject_rows(lines, item, placeholder_groups.get(item, []), lang=lang)
            continue

        parts = _row_to_quickstatements_parts(row, qs_item=item, placeholder_to_qs_target={})
        if parts:
            lines.append("\t".join(parts))

    return "\n".join(lines)
