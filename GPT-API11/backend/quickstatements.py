"""Conversion utilities for turning approved rows into Wikibase QuickStatements output."""

from __future__ import annotations
import re
from typing import Any, Iterable
from urllib.parse import urlparse
from .extractor.ontology import ONTOLOGY
from .state import canonical_row_key, norm

PLACEHOLDER_PREFIXES = ("QNEW", "NEW:")
PLACEHOLDER_LABEL_FIELDS = (
    ("item", "itemLabel"),
    ("value", "valueLabel"),
    ("qualifierValue", "qualifierValueLabel"),
)
ENTITY_LABEL_FIELDS = (
    ("item", "itemLabel"),
    ("value", "valueLabel"),
    ("qualifierValue", "qualifierValueLabel"),
)
PLACEHOLDER_VALUE_FIELDS = ("item", "value", "qualifierValue")
QUALIFIER_FIELDS = ("qualifierProperty", "qualifierPropertyLabel", "qualifierValue", "qualifierValueLabel")
ENTITY_ID_RE = re.compile(r"^[QP]\d+$")
QID_RE = re.compile(r"^Q\d+$")
TIME_PROPERTY_HINT_RE = re.compile(r"\b(date|time)\b", re.IGNORECASE)
QS_TIME_LITERAL_RE = re.compile(r"^[+-]\d{4,}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z/\d{1,2}$")
ISO_DATE_RE = re.compile(r"^(?P<year>\d{4,})-(?P<month>\d{2})-(?P<day>\d{2})$")
ISO_MONTH_RE = re.compile(r"^(?P<year>\d{4,})-(?P<month>\d{2})$")
ISO_YEAR_RE = re.compile(r"^(?P<year>\d{4,})$")
ISO_DATETIME_RE = re.compile(
    r"^(?P<year>\d{4,})-(?P<month>\d{2})-(?P<day>\d{2})T"
    r"(?P<hour>\d{2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?Z$"
)

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

def _normalize_label_key(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).casefold()
    text = "".join(ch if ch.isalnum() else " " for ch in text)
    return " ".join(text.split())

def _escape_literal(text: str) -> str:
    return text.replace('"', '""')

def _property_hints(prop: Any, prop_label: Any) -> list[str]:
    hints: list[str] = []
    if isinstance(prop_label, str) and prop_label.strip():
        hints.append(prop_label.strip())

    prop_token = _normalize_entity_token(prop)
    if prop_token.startswith("P"):
        ontology_label = ONTOLOGY.index.get("property_id_to_label", {}).get(prop_token)
        if isinstance(ontology_label, str) and ontology_label.strip():
            hints.append(ontology_label.strip())

    row = ONTOLOGY.index.get("by_entity", {}).get(prop) if isinstance(prop, str) else None
    if isinstance(row, dict):
        label = row.get("entityLabel")
        description = row.get("entityDescription")
        if isinstance(label, str) and label.strip():
            hints.append(label.strip())
        if isinstance(description, str) and description.strip():
            hints.append(description.strip())

    return hints

def _is_time_property(prop: Any, prop_label: Any) -> bool:
    return any(TIME_PROPERTY_HINT_RE.search(hint) for hint in _property_hints(prop, prop_label))

def _format_time_literal(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if QS_TIME_LITERAL_RE.fullmatch(text):
        return text

    match = ISO_DATETIME_RE.fullmatch(text)
    if match:
        year = f"+{match.group('year')}"
        month = match.group("month")
        day = match.group("day")
        hour = match.group("hour")
        minute = match.group("minute")
        second = match.group("second") or "00"
        precision = "11" if hour == "00" and minute == "00" and second == "00" else "14"
        return f"{year}-{month}-{day}T{hour}:{minute}:{second}Z/{precision}"

    match = ISO_DATE_RE.fullmatch(text)
    if match:
        return f"+{match.group('year')}-{match.group('month')}-{match.group('day')}T00:00:00Z/11"

    match = ISO_MONTH_RE.fullmatch(text)
    if match:
        return f"+{match.group('year')}-{match.group('month')}-00T00:00:00Z/10"

    match = ISO_YEAR_RE.fullmatch(text)
    if match:
        return f"+{match.group('year')}-00-00T00:00:00Z/9"

    return None

def _qs_value_term(
    value: Any,
    *,
    prop: Any,
    prop_label: Any,
    placeholder_to_qs_target: dict[str, str],
) -> str:
    if _is_time_property(prop, prop_label):
        formatted_time = _format_time_literal(value)
        if formatted_time:
            return formatted_time
    return _qs_term(str(value or ""), placeholder_to_qs_target)

def _qs_term(token: str, placeholder_to_qs_target: dict[str, str]) -> str:
    token = _normalize_entity_token(token)
    if token.startswith(PLACEHOLDER_PREFIXES):
        return placeholder_to_qs_target.get(token, token)
    if ENTITY_ID_RE.fullmatch(token.upper()):
        return token
    return f'"{_escape_literal(token)}"'

def _is_placeholder(token: Any) -> bool:
    return isinstance(token, str) and token.startswith(PLACEHOLDER_PREFIXES)

def _normalize_entity_id(value: Any) -> str:
    token = _normalize_entity_token(value)
    token_upper = token.upper()
    return token_upper if ENTITY_ID_RE.fullmatch(token_upper) else ""

def _normalize_qid(value: Any) -> str:
    token = _normalize_entity_id(value)
    return token if QID_RE.fullmatch(token) else ""

def _is_entity_id(value: Any) -> bool:
    return bool(_normalize_entity_id(value))

def _normalize_property_token(value: Any, *, label: Any = None) -> str:
    token = _normalize_entity_token(value)
    if token.startswith("P"):
        return token

    property_labels = ONTOLOGY.index.get("property_labels", {})
    for candidate in (label, value):
        raw_key = norm(candidate) if isinstance(candidate, str) else ""
        if raw_key:
            entity = property_labels.get(raw_key)
            normalized = _normalize_entity_token(entity)
            if normalized.startswith("P"):
                return normalized

        key = _normalize_label_key(candidate)
        if not key or key == raw_key:
            continue
        for existing_key, entity in property_labels.items():
            if _normalize_label_key(existing_key) != key:
                continue
            normalized = _normalize_entity_token(entity)
            if normalized.startswith("P"):
                return normalized
    return ""

def _append_unique_mapping(out: dict[str, list[str]], key: str, value: str) -> None:
    values = out.setdefault(key, [])
    if value not in values:
        values.append(value)

def _iter_labeled_entities(rows: Iterable[dict[str, Any]]):
    for row in rows:
        if not isinstance(row, dict):
            continue
        for entity_key, label_key in ENTITY_LABEL_FIELDS:
            entity = row.get(entity_key)
            label = row.get(label_key)
            normalized_entity = _normalize_entity_id(entity)
            if not normalized_entity or not isinstance(label, str):
                continue
            cleaned = label.strip()
            if cleaned:
                yield normalized_entity, cleaned

def _build_entity_label_index(*row_groups: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for rows in row_groups:
        for entity, label in _iter_labeled_entities(rows):
            key = _normalize_label_key(label)
            if key:
                _append_unique_mapping(out, key, entity)

    for row in ONTOLOGY.index.get("raw", []):
        if not isinstance(row, dict):
            continue
        entity = _normalize_entity_id(row.get("entity"))
        if not entity:
            continue
        for label in (row.get("entityLabel"), row.get("entityAltLabel")):
            key = _normalize_label_key(label)
            if key:
                _append_unique_mapping(out, key, entity)

    return out

def _collect_entity_value_properties(
    rows: Iterable[dict[str, Any]],
    *,
    property_field: str,
    value_field: str,
) -> set[str]:
    counts: dict[str, dict[str, int]] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        prop = _normalize_entity_token(row.get(property_field))
        if not prop.startswith("P"):
            continue
        value = row.get(value_field)
        if value is None or value == "":
            continue
        if _is_placeholder(value):
            continue

        bucket = counts.setdefault(prop, {"entity": 0, "literal": 0})
        if _is_entity_id(value):
            bucket["entity"] += 1
        else:
            bucket["literal"] += 1

    return {
        prop
        for prop, bucket in counts.items()
        if bucket["entity"] > 0 and bucket["literal"] == 0
    }

def _resolve_entity_target(
    value: Any,
    *,
    label: Any,
    entity_label_index: dict[str, list[str]],
) -> str:
    normalized_entity = _normalize_entity_id(value)
    if normalized_entity:
        return normalized_entity

    for candidate in (label, value):
        key = _normalize_label_key(candidate)
        if not key:
            continue
        matches = entity_label_index.get(key, [])
        if len(matches) == 1:
            return str(matches[0])
    return ""

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
    reference_rows: Iterable[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str], dict[int, int | None]]:
    """
    Remove or downgrade rows that cannot be represented safely in Wikibase Cloud
    QuickStatements:
    - brand-new placeholder objects (`value = NEW:*`) are dropped
    - brand-new placeholder qualifier values are removed from the row
    """
    row_list = [row for row in rows if isinstance(row, dict)]
    reference_row_list = [row for row in (reference_rows or []) if isinstance(row, dict)]
    # Learn which properties are entity-valued from the existing KB snapshot when
    # available, then use that to convert stray labels like "software" into QIDs.
    reference_entity_value_properties = _collect_entity_value_properties(
        reference_row_list,
        property_field="property",
        value_field="value",
    )
    row_entity_value_properties = _collect_entity_value_properties(
        row_list,
        property_field="property",
        value_field="value",
    )
    entity_value_properties = reference_entity_value_properties | row_entity_value_properties
    reference_entity_qualifier_properties = _collect_entity_value_properties(
        reference_row_list,
        property_field="qualifierProperty",
        value_field="qualifierValue",
    )
    row_entity_qualifier_properties = _collect_entity_value_properties(
        row_list,
        property_field="qualifierProperty",
        value_field="qualifierValue",
    )
    entity_qualifier_properties = reference_entity_qualifier_properties | row_entity_qualifier_properties
    entity_label_index = _build_entity_label_index(reference_row_list, row_list)

    sanitized: list[dict[str, Any]] = []
    warnings: list[str] = []
    # index_map keeps a link back to the original row positions so the API can report
    # how many rows were skipped or collapsed after QuickStatements sanitization.
    index_map: dict[int, int | None] = {}
    key_to_index: dict[tuple[Any, ...], int] = {}

    for idx, row in enumerate(row_list):
        candidate = dict(row)
        item = candidate.get("item")
        value = candidate.get("value")
        qualifier_value = candidate.get("qualifierValue")
        summary = _row_summary(candidate)
        prop_token = _normalize_property_token(candidate.get("property"), label=candidate.get("propertyLabel"))
        qualifier_prop_token = _normalize_property_token(
            candidate.get("qualifierProperty"),
            label=candidate.get("qualifierPropertyLabel"),
        )

        if _is_placeholder(item):
            if not allow_subject_placeholders:
                item_label = candidate.get("itemLabel") or candidate.get("item")
                warnings.append(
                    f"Dropped QuickStatements row for {summary}: subject {item_label!r} is still unresolved. Fill in its QID before generating Step 2."
                )
                index_map[idx] = None
                continue
        else:
            resolved_item = _resolve_entity_target(
                item,
                label=candidate.get("itemLabel"),
                entity_label_index=entity_label_index,
            )
            if resolved_item:
                candidate["item"] = resolved_item
            else:
                item_label = candidate.get("itemLabel") or item
                warnings.append(
                    f"Dropped QuickStatements row for {summary}: subject {item_label!r} must resolve to an existing entity id."
                )
                index_map[idx] = None
                continue

        if not prop_token:
            prop_label = candidate.get("propertyLabel") or candidate.get("property")
            warnings.append(
                f"Dropped QuickStatements row for {summary}: property {prop_label!r} is not a known ontology property."
            )
            index_map[idx] = None
            continue
        candidate["property"] = prop_token

        if (candidate.get("qualifierProperty") or candidate.get("qualifierPropertyLabel")) and not qualifier_prop_token:
            qualifier_label = candidate.get("qualifierPropertyLabel") or candidate.get("qualifierProperty")
            warnings.append(
                f"Removed QuickStatements qualifier from {summary}: qualifier property {qualifier_label!r} is not a known ontology property."
            )
            _clear_qualifier(candidate)
            qualifier_prop_token = ""
        elif qualifier_prop_token:
            candidate["qualifierProperty"] = qualifier_prop_token

        if prop_token in entity_value_properties and not _is_entity_id(value):
            resolved_value = _resolve_entity_target(
                value,
                label=candidate.get("valueLabel"),
                entity_label_index=entity_label_index,
            )
            if resolved_value:
                candidate["value"] = resolved_value
                value = resolved_value
            else:
                value_label = candidate.get("valueLabel") or value
                warnings.append(
                    f"Dropped QuickStatements row for {summary}: value {value_label!r} must resolve to an existing entity id for {candidate.get('propertyLabel') or prop_token or 'this property'}."
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
        elif qualifier_prop_token in entity_qualifier_properties and qualifier_value and not _is_entity_id(qualifier_value):
            resolved_qualifier = _resolve_entity_target(
                qualifier_value,
                label=candidate.get("qualifierValueLabel"),
                entity_label_index=entity_label_index,
            )
            if resolved_qualifier:
                candidate["qualifierValue"] = resolved_qualifier
            else:
                qualifier_label = candidate.get("qualifierValueLabel") or qualifier_value
                warnings.append(
                    f"Removed QuickStatements qualifier from {summary}: qualifier value {qualifier_label!r} must resolve to an existing entity id for {candidate.get('qualifierPropertyLabel') or qualifier_prop_token or 'this qualifier'}."
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
    reference_rows: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_bindings, binding_warnings = _normalize_bindings(bindings)
    bound_rows = apply_placeholder_bindings(rows, normalized_bindings)
    # Step 2 only works after placeholder subjects are rebound to real QIDs; any
    # rows still pointing at placeholders are skipped with warnings below.
    sanitized_rows, qs_warnings, row_index_map = sanitize_rows_for_quickstatements(
        bound_rows,
        allow_subject_placeholders=False,
        reference_rows=reference_rows,
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
    prop = _normalize_property_token(row.get("property", ""), label=row.get("propertyLabel"))
    value = _normalize_entity_token(row.get("value", ""))
    if not (qs_item and prop and value and prop.startswith("P")):
        return []

    parts = [
        qs_item,
        prop,
        _qs_value_term(
            row.get("value", ""),
            prop=row.get("property"),
            prop_label=row.get("propertyLabel"),
            placeholder_to_qs_target=placeholder_to_qs_target,
        ),
    ]
    qp = _normalize_property_token(row.get("qualifierProperty", "") or "", label=row.get("qualifierPropertyLabel"))
    qv = _normalize_entity_token(row.get("qualifierValue", "") or "")
    if qp and qv and qp.startswith("P"):
        parts.extend([
            qp,
            _qs_value_term(
                row.get("qualifierValue", ""),
                prop=row.get("qualifierProperty"),
                prop_label=row.get("qualifierPropertyLabel"),
                placeholder_to_qs_target=placeholder_to_qs_target,
            ),
        ])
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
        if not (ENTITY_ID_RE.fullmatch(item.upper()) or item.startswith(PLACEHOLDER_PREFIXES)):
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
