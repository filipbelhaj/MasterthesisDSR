"""Context building, entity reuse, and retrieval helpers for prompt construction."""

from collections import OrderedDict
import logging
import math
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from ..core.config import (
    EMBEDDING_MODEL,
    EMBEDDING_RERANK_CANDIDATES,
    ENTITY_NEIGHBORHOOD_PER_ENTITY,
    ENTITY_NEIGHBORHOOD_SHARE,
    FTS_CANDIDATES,
    ROW_EMBEDDING_CACHE_MAX,
    get_client,
)
from ..state import canonical_row_key, fts_candidate_indices, norm, normalize_key_value
from .ontology import STATEMENT_FIELDS

LOGGER = logging.getLogger(__name__)

BARE_ENTITY_ID_RE = re.compile(r"^[QPqp][0-9]+$")
ENTITY_LABEL_FIELDS = (("item", "itemLabel"), ("value", "valueLabel"))
KB_ENTITY_FIELDS = ("item", "value", "qualifierValue", "property", "qualifierProperty")
PROPOSAL_ENTITY_FIELDS = ("item", "value", "qualifierValue")
PLACEHOLDER_RESOLUTION_FIELDS = (
    ("item", "itemLabel"),
    ("value", "valueLabel"),
    ("qualifierValue", "qualifierValueLabel"),
)
REFERENCE_SEGMENT_SPLIT_RE = re.compile(r"\s*[,;:]\s*")
ROMAN_NUMERAL_RE = re.compile(r"(?i)^[ivxlcdm]+$")
INLINE_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
NEWLINE_PADDING_RE = re.compile(r"[ \t]*\n[ \t]*")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
PLACEHOLDER_ENTITY_RE = re.compile(r"^NEW:entity_(\d+)$")
TITLE_TOKEN_RE = re.compile(r"(?u)[^\W_]+(?:-[^\W_]+)*")
EMBEDDING_DEGRADED_WARNING = "Semantic reranking was skipped because embeddings could not be generated."
ROW_EMBEDDING_CACHE: "OrderedDict[Tuple[Any, ...], List[float]]" = OrderedDict()

def clear_row_embedding_cache() -> None:
    ROW_EMBEDDING_CACHE.clear()

def _get_cached_row_embedding(key: Tuple[Any, ...]) -> Optional[List[float]]:
    vector = ROW_EMBEDDING_CACHE.get(key)
    if vector is not None:
        ROW_EMBEDDING_CACHE.move_to_end(key)
    return vector

def _store_row_embedding(key: Tuple[Any, ...], vector: List[float]) -> None:
    if ROW_EMBEDDING_CACHE_MAX <= 0:
        return
    ROW_EMBEDDING_CACHE[key] = vector
    ROW_EMBEDDING_CACHE.move_to_end(key)
    # Keep this as a simple LRU cache: repeated retrieval rounds within a session
    # often hit the same KB rows, so caching saves the most expensive rerank step.
    while len(ROW_EMBEDDING_CACHE) > ROW_EMBEDDING_CACHE_MAX:
        ROW_EMBEDDING_CACHE.popitem(last=False)

def append_unique_mapping(out: Dict[str, List[str]], key: str, value: str) -> None:
    values = out.setdefault(key, [])
    if value not in values:
        values.append(value)

def append_unique_text(out: List[str], value: str) -> None:
    if value not in out:
        out.append(value)

def normalize_label_for_match(label: Any) -> str:
    if label is None:
        return ""
    text = str(label).casefold()
    text = "".join(ch if ch.isalnum() else " " for ch in text)
    return " ".join(text.split())

def normalize_input_text(input_text: str) -> str:
    text = (input_text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = NEWLINE_PADDING_RE.sub("\n", text)
    text = INLINE_WHITESPACE_RE.sub(" ", text)
    text = MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()

def _normalized_haystack(text: str, limit: int = 12000) -> str:
    return normalize_label_for_match(text)[:limit]

def truncate_str(value: Any, limit: int) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"

def _iter_clean_labels(base_rows: List[Dict[str, Any]], label_key: str):
    for row in base_rows:
        if not isinstance(row, dict):
            continue
        label = row.get(label_key)
        if isinstance(label, str):
            cleaned = label.strip()
            if cleaned:
                yield cleaned

def _iter_labeled_entities(base_rows: List[Dict[str, Any]], *, entity_filter):
    for row in base_rows:
        if not isinstance(row, dict):
            continue
        for entity_key, label_key in ENTITY_LABEL_FIELDS:
            entity = row.get(entity_key)
            label = row.get(label_key)
            if not entity_filter(entity) or not isinstance(label, str):
                continue
            cleaned = label.strip()
            if cleaned:
                yield entity, cleaned

def _looks_like_structured_reference(text: Any) -> bool:
    tokens = normalize_label_for_match(text).split()
    if len(tokens) < 2 or len(tokens) > 8:
        return False
    if not any(ch.isalpha() for ch in tokens[0]):
        return False
    tail_tokens = tokens[1:]
    if any(any(ch.isdigit() for ch in token) for token in tail_tokens):
        return True
    if any(ROMAN_NUMERAL_RE.fullmatch(token) for token in tail_tokens):
        return True
    return len(tail_tokens) == 1 and len(tail_tokens[0]) <= 3

def _structured_reference_core_text(label: Any) -> Optional[str]:
    if label is None:
        return None
    text = str(label).strip()
    if not text:
        return None

    segments = [segment.strip() for segment in REFERENCE_SEGMENT_SPLIT_RE.split(text) if segment.strip()]
    if segments:
        for candidate in segments[:2]:
            if _looks_like_structured_reference(candidate):
                return candidate
    if _looks_like_structured_reference(text):
        return text
    return None

def _title_tokens(text: str) -> List[str]:
    return TITLE_TOKEN_RE.findall(text)

def _is_all_caps_token(token: str) -> bool:
    if len(token) < 2:
        return False
    if not all(ch.isalnum() or ch == "-" for ch in token):
        return False
    return any(ch.isalpha() and ch.isupper() for ch in token) and all(
        (not ch.isalpha()) or ch.isupper() for ch in token
    )

def _title_shortforms(title: Any) -> List[str]:
    if title is None:
        return []
    text = str(title).strip()
    if not text:
        return []

    out: List[str] = []
    all_caps = [
        token for token in _title_tokens(text)
        if _is_all_caps_token(token) and not token.isdigit()
    ]
    for token in all_caps:
        append_unique_text(out, token)

    titled_tokens = [
        token for token in _title_tokens(text)
        if token[:1].isupper()
    ]
    if len(titled_tokens) >= 2:
        acronym = "".join(token[0].upper() for token in titled_tokens)
        if len(acronym) >= 2:
            append_unique_text(out, acronym)
    return out

def _structured_reference_alias_texts(label: Any) -> List[str]:
    text = ("" if label is None else str(label)).strip()
    if not text:
        return []

    reference = _structured_reference_core_text(text)
    if not reference:
        return []

    aliases: List[str] = []
    parts = [part.strip() for part in REFERENCE_SEGMENT_SPLIT_RE.split(text) if part.strip()]
    title_candidates: List[str] = []
    if len(parts) >= 2:
        for part in reversed(parts):
            if part != reference:
                title_candidates.append(part)
                break

    for raw_title in title_candidates:
        title = raw_title.strip()
        if not title:
            continue
        append_unique_text(aliases, f"{title} {reference}")
        append_unique_text(aliases, f"{reference} {title}")
        for shortform in _title_shortforms(title):
            if normalize_label_for_match(shortform) == normalize_label_for_match(title):
                continue
            append_unique_text(aliases, f"{shortform} {reference}")
            append_unique_text(aliases, f"{reference} {shortform}")

    append_unique_text(aliases, reference)
    return aliases

def _structured_reference_kind(label: Any) -> Optional[str]:
    core = _structured_reference_core_text(label)
    if not core:
        return None
    tokens = normalize_label_for_match(core).split()
    return tokens[0] if tokens else None

def _label_match_entries(label: Any) -> List[Tuple[str, str]]:
    text = ("" if label is None else str(label)).strip()
    if not text:
        return []

    entries: List[Tuple[str, str]] = []
    seen_keys = set()

    def add(display_text: str) -> None:
        display = display_text.strip()
        key = normalize_label_for_match(display)
        if not display or not key or key in seen_keys:
            return
        seen_keys.add(key)
        entries.append((display, key))

    add(text)
    for alias in _structured_reference_alias_texts(text):
        add(alias)
    return entries

def _matching_label_entry(
    label: Any,
    haystack: str,
    *,
    label_to_entities: Optional[Dict[str, List[str]]] = None,
    entity: Optional[str] = None,
) -> Optional[Tuple[str, str]]:
    for display_text, key in _label_match_entries(label):
        if key not in haystack:
            continue
        if label_to_entities is None:
            return display_text, key
        mapped = label_to_entities.get(key, [])
        if len(mapped) == 1 and (entity is None or mapped[0] == entity):
            return display_text, key
    return None

def _is_entity_uri(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if "://" not in value or "/entity/" not in value:
        return False
    tail = value.rsplit("/", 1)[-1]
    return bool(BARE_ENTITY_ID_RE.match(tail))

def _structured_reference_style_index(base_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    item_kinds: Dict[Any, str] = {}
    item_labels: Dict[Any, str] = {}
    item_property_labels: Dict[Any, List[str]] = {}

    for row in base_rows:
        if not isinstance(row, dict):
            continue
        item = row.get("item")
        label = row.get("itemLabel")
        if not _is_entity_uri(item) or not isinstance(label, str) or not label.strip():
            continue
        kind = _structured_reference_kind(label)
        if not kind:
            continue

        item_key = normalize_key_value(item)
        if item_key is None:
            continue
        if normalize_key_value(row.get("property")) is None:
            continue

        item_kinds.setdefault(item_key, kind)
        item_labels.setdefault(item_key, label.strip())

        property_label = row.get("propertyLabel") or row.get("property")
        if isinstance(property_label, str) and property_label.strip():
            labels = item_property_labels.setdefault(item_key, [])
            cleaned_label = property_label.strip()
            if cleaned_label not in labels:
                labels.append(cleaned_label)

    return {
        "item_kinds": item_kinds,
        "item_labels": item_labels,
        "item_property_labels": item_property_labels,
    }

def structured_reference_style_examples(
    entity_catalog: List[Dict[str, str]],
    base_rows: List[Dict[str, Any]],
    *,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    style = _structured_reference_style_index(base_rows)
    if not style["item_kinds"] or limit <= 0:
        return []

    out: List[Dict[str, Any]] = []
    seen = set()
    for entry in entity_catalog:
        if not isinstance(entry, dict):
            continue
        entity_key = normalize_key_value(entry.get("entity"))
        if entity_key is None or entity_key in seen:
            continue
        kind = style["item_kinds"].get(entity_key)
        if not kind:
            continue
        seen.add(entity_key)
        out.append({
            "entity": entry.get("entity"),
            "label": style["item_labels"].get(entity_key) or entry.get("canonical_label") or entry.get("label"),
            "reference_kind": kind,
            "direct_properties_used_in_kb": style["item_property_labels"].get(entity_key, [])[:6],
        })
        if len(out) >= limit:
            break
    return out

def existing_item_labels(input_text: str, base_rows: List[Dict[str, Any]]) -> List[str]:
    haystack = _normalized_haystack(input_text)
    if not haystack:
        return []

    out: List[str] = []
    seen = set()
    for label_text in _iter_clean_labels(base_rows, "itemLabel"):
        label_key = normalize_label_for_match(label_text)
        if not label_key or label_key in seen or not _matching_label_entry(label_text, haystack):
            continue
        seen.add(label_key)
        out.append(label_text)
    return out

def existing_entity_catalog_for_input(
    input_text: str,
    base_rows: List[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, str]]:
    if limit <= 0:
        return []

    haystack = _normalized_haystack(input_text)
    if not haystack:
        return []

    label_to_uris = _build_label_index(base_rows, entity_filter=_is_entity_uri)
    out: List[Dict[str, str]] = []
    seen = set()
    for entity, canonical_label in _iter_labeled_entities(base_rows, entity_filter=_is_entity_uri):
        if len(out) >= limit:
            break

        match = _matching_label_entry(
            canonical_label,
            haystack,
            label_to_entities=label_to_uris,
            entity=entity,
        )
        if match is None:
            continue
        matched_display, matched_key = match

        seen_key = (matched_key, entity)
        if seen_key in seen:
            continue
        seen.add(seen_key)

        entry = {"label": matched_display, "entity": entity}
        if canonical_label.casefold() != matched_display.casefold():
            entry["canonical_label"] = canonical_label
        out.append(entry)

    return out

def entity_ids_from_catalog(entity_catalog: List[Dict[str, str]]) -> set:
    return {
        normalize_key_value(entry.get("entity"))
        for entry in entity_catalog
        if isinstance(entry, dict) and normalize_key_value(entry.get("entity")) is not None
    }

def _infer_entity_prefix(base_rows: List[Dict[str, Any]]) -> Optional[str]:
    for row in base_rows:
        if not isinstance(row, dict):
            continue
        for key in KB_ENTITY_FIELDS:
            value = row.get(key)
            if not isinstance(value, str):
                continue
            if "://" not in value or "/entity/" not in value:
                continue
            prefix = value.split("/entity/", 1)[0].rstrip("/") + "/entity/"
            if prefix.startswith("http"):
                return prefix
    return None

def _expand_bare_entity_id(value: Any, entity_prefix: Optional[str]) -> Any:
    if not isinstance(value, str) or not entity_prefix:
        return value
    text = value.strip()
    if not BARE_ENTITY_ID_RE.match(text):
        return value
    return f"{entity_prefix}{text.upper()}"

def _is_placeholder_entity(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("NEW:")

def _build_label_index(base_rows: List[Dict[str, Any]], *, entity_filter) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for entity, label in _iter_labeled_entities(base_rows, entity_filter=entity_filter):
        for _, key in _label_match_entries(label):
            append_unique_mapping(out, key, entity)
    return out

def _fuzzy_resolve_label(label_key: str, label_to_uris: Dict[str, List[str]]) -> Optional[str]:
    label_key = (label_key or "").strip()
    if len(label_key) < 9:
        return None
    tokens = set(label_key.split())
    if len(tokens) < 2:
        return None

    best_ratio = 0.0
    second_ratio = 0.0
    best_uri: Optional[str] = None
    for existing_key, uris in label_to_uris.items():
        if len(uris) != 1 or not existing_key:
            continue
        ex_tokens = existing_key.split()
        if not tokens.intersection(ex_tokens):
            continue
        if abs(len(existing_key) - len(label_key)) > max(14, len(label_key) // 2):
            continue
        ratio = SequenceMatcher(None, label_key, existing_key).ratio()
        if ratio > best_ratio:
            second_ratio = best_ratio
            best_ratio = ratio
            best_uri = uris[0]
        elif ratio > second_ratio:
            second_ratio = ratio

    if best_ratio >= 0.965 and (best_ratio - second_ratio) >= 0.02:
        return best_uri
    return None

def _normalize_row_entity_ids(row: Dict[str, Any], entity_prefix: Optional[str]) -> None:
    for field in PROPOSAL_ENTITY_FIELDS:
        row[field] = _expand_bare_entity_id(row.get(field), entity_prefix)

def _build_placeholder_to_label_key(base_rows: List[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for entity, label in _iter_labeled_entities(base_rows, entity_filter=_is_placeholder_entity):
        label_key = normalize_label_for_match(label)
        if label_key and entity not in out:
            out[entity] = label_key
    return out

def _collect_used_placeholders(*row_groups: List[Dict[str, Any]]) -> set[str]:
    used: set[str] = set()
    for rows in row_groups:
        for row in rows:
            if not isinstance(row, dict):
                continue
            for field in PROPOSAL_ENTITY_FIELDS:
                value = row.get(field)
                if isinstance(value, str) and value.startswith("NEW:"):
                    used.add(value)
    return used

def _next_placeholder_index(used_placeholders: set[str]) -> int:
    next_index = 1
    for placeholder in used_placeholders:
        match = PLACEHOLDER_ENTITY_RE.fullmatch(placeholder)
        if match:
            next_index = max(next_index, int(match.group(1)) + 1)
    return next_index

class _PlaceholderResolver:
    def __init__(self, base_rows: List[Dict[str, Any]], proposal_rows: List[Dict[str, Any]]) -> None:
        self.entity_prefix = _infer_entity_prefix(base_rows)
        self.label_to_uris = _build_label_index(base_rows, entity_filter=_is_entity_uri)
        self.label_to_placeholders = _build_label_index(base_rows, entity_filter=_is_placeholder_entity)
        self.placeholder_by_label: Dict[str, str] = {}
        self.label_by_placeholder = _build_placeholder_to_label_key(base_rows)
        self.used_placeholders = _collect_used_placeholders(base_rows, proposal_rows)
        self.next_placeholder_index = _next_placeholder_index(self.used_placeholders)

    def fresh_placeholder(self) -> str:
        while True:
            placeholder = f"NEW:entity_{self.next_placeholder_index}"
            self.next_placeholder_index += 1
            if placeholder not in self.used_placeholders:
                self.used_placeholders.add(placeholder)
                return placeholder

    def resolve_field(self, row: Dict[str, Any], field: str, label_field: str) -> None:
        value = row.get(field)
        label_key = normalize_label_for_match(row.get(label_field))
        if not (_is_placeholder_entity(value) and label_key):
            return

        candidates = self.label_to_uris.get(label_key, [])
        if len(candidates) == 1:
            row[field] = candidates[0]
            return
        # Ambiguous existing matches are left unresolved on purpose: in practice it is
        # safer to keep a NEW:* placeholder than to silently bind the wrong entity.
        if candidates:
            return

        fuzzy = _fuzzy_resolve_label(label_key, self.label_to_uris)
        if fuzzy:
            row[field] = fuzzy
            return

        placeholders = self.label_to_placeholders.get(label_key, [])
        if len(placeholders) == 1:
            row[field] = placeholders[0]
            return

        if label_key in self.placeholder_by_label:
            row[field] = self.placeholder_by_label[label_key]
            return

        claimed_label = self.label_by_placeholder.get(value)
        row[field] = self.fresh_placeholder() if claimed_label is not None and claimed_label != label_key else value
        self.used_placeholders.add(row[field])
        self.placeholder_by_label[label_key] = row[field]
        self.label_by_placeholder[row[field]] = label_key

def resolve_existing_entities(
    proposal_rows: List[Dict[str, Any]],
    base_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    resolver = _PlaceholderResolver(base_rows, proposal_rows)

    out: List[Dict[str, Any]] = []
    for row in proposal_rows:
        if not isinstance(row, dict):
            continue
        resolved = dict(row)
        _normalize_row_entity_ids(resolved, resolver.entity_prefix)
        for field, label_field in PLACEHOLDER_RESOLUTION_FIELDS:
            resolver.resolve_field(resolved, field, label_field)
        out.append(resolved)

    return out

def _row_text_for_embedding(row: Dict[str, Any]) -> str:
    parts = [
        row.get("itemLabel") or row.get("item"),
        row.get("propertyLabel") or row.get("property"),
        row.get("valueLabel"),
    ]
    if parts[-1] is None:
        parts[-1] = row.get("value")
    qprop = row.get("qualifierPropertyLabel") or row.get("qualifierProperty")
    qval = row.get("qualifierValueLabel")
    if qval is None:
        qval = row.get("qualifierValue")
    if qprop and qval:
        parts.append(f"{qprop}: {qval}")
    return " | ".join(str(part) for part in parts if part is not None).replace("\n", " ").strip()

def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    denominator = math.sqrt(norm_a) * math.sqrt(norm_b)
    return (dot / denominator) if denominator else -1.0

def _embed_texts(
    texts: List[str],
    *,
    warnings: Optional[List[str]] = None,
    purpose: str = "embedding request",
) -> Optional[List[List[float]]]:
    if not texts:
        return []

    def warn_embedding_failure(message: str, *, exc_info: bool = False) -> None:
        if warnings is not None:
            append_unique_text(warnings, EMBEDDING_DEGRADED_WARNING)
        LOGGER.warning(message, exc_info=exc_info)

    try:
        response = get_client().embeddings.create(model=EMBEDDING_MODEL, input=texts)
        data = getattr(response, "data", None)
        if not data and isinstance(response, dict):
            data = response.get("data")
        if not isinstance(data, list):
            warn_embedding_failure(
                f"Embedding API returned an unexpected payload during {purpose}.",
            )
            return None

        vectors: List[List[float]] = []
        for item in data:
            embedding = item.get("embedding") if isinstance(item, dict) else getattr(item, "embedding", None)
            if not isinstance(embedding, list):
                warn_embedding_failure(
                    f"Embedding API returned an item without a valid vector during {purpose}.",
                )
                return None
            vectors.append([float(value) for value in embedding])
        return vectors
    except Exception:
        warn_embedding_failure(
            f"Failed during {purpose} for {len(texts)} text(s).",
            exc_info=True,
        )
        return None

def _compact_row_for_prompt(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in STATEMENT_FIELDS:
        if key not in row:
            continue
        value = row.get(key)
        if value is None:
            continue
        out[key] = truncate_str(value, 420)
    return out

def _try_add_preview_row(
    row: Dict[str, Any],
    *,
    selected: List[Dict[str, Any]],
    seen_keys: set,
) -> bool:
    key = canonical_row_key(row)
    if key in seen_keys:
        return False
    seen_keys.add(key)
    selected.append(row)
    return True

def _preview_item_key(row: Dict[str, Any]) -> Any:
    return (
        normalize_key_value(row.get("item"))
        or normalize_key_value(row.get("itemLabel"))
        or canonical_row_key(row)
    )

def _preview_property_key(row: Dict[str, Any]) -> Any:
    return (
        normalize_key_value(row.get("property"))
        or normalize_key_value(row.get("propertyLabel"))
        or canonical_row_key(row)
    )

def _diversified_preview_rows(rows: List[Dict[str, Any]], topk: int) -> List[Dict[str, Any]]:
    if not rows or topk <= 0:
        return []

    per_item_cap = max(2, min(4, math.ceil(topk / 20)))
    per_property_cap = max(4, min(10, math.ceil(topk / 8)))
    passes = [
        (1, max(2, per_property_cap // 2)),
        (per_item_cap, per_property_cap),
        (0, 0),
    ]

    selected: List[Dict[str, Any]] = []
    selected_keys = set()
    item_counts: Dict[Any, int] = {}
    property_counts: Dict[Any, int] = {}

    for item_cap, property_cap in passes:
        for row in rows:
            if not isinstance(row, dict):
                continue

            row_key = canonical_row_key(row)
            if row_key in selected_keys:
                continue

            item_key = _preview_item_key(row)
            property_key = _preview_property_key(row)
            if item_cap and item_counts.get(item_key, 0) >= item_cap:
                continue
            if property_cap and property_counts.get(property_key, 0) >= property_cap:
                continue

            selected.append(row)
            selected_keys.add(row_key)
            item_counts[item_key] = item_counts.get(item_key, 0) + 1
            property_counts[property_key] = property_counts.get(property_key, 0) + 1
            if len(selected) >= topk:
                return selected[:topk]

    return selected[:topk]

def _matching_entity_anchor(row: Dict[str, Any], entity_ids: set) -> Any:
    for field in PROPOSAL_ENTITY_FIELDS:
        value = normalize_key_value(row.get(field))
        if value in entity_ids:
            return value
    return None

def _entity_neighborhood_preview_rows(
    rows: List[Dict[str, Any]],
    topk: int,
    matched_entity_ids: Optional[set],
) -> List[Dict[str, Any]]:
    if not rows or topk <= 0 or not matched_entity_ids:
        return []

    candidates = [
        row for row in rows
        if isinstance(row, dict) and _matching_entity_anchor(row, matched_entity_ids) is not None
    ]
    if not candidates:
        return []

    reserve_by_share = int(math.ceil(topk * max(0.0, float(ENTITY_NEIGHBORHOOD_SHARE))))
    per_entity_cap = max(1, int(ENTITY_NEIGHBORHOOD_PER_ENTITY))
    # Reserve part of the prompt budget for rows around already-matched entities so the
    # chat model sees local graph structure, not just isolated top-ranked statements.
    reserve_count = min(topk, len(candidates), reserve_by_share, len(matched_entity_ids) * per_entity_cap)
    if reserve_count <= 0:
        return []

    prioritized = _diversified_preview_rows(candidates, len(candidates))
    selected: List[Dict[str, Any]] = []
    anchor_counts: Dict[Any, int] = {}
    seen_keys = set()
    for row in prioritized:
        row_key = canonical_row_key(row)
        if row_key in seen_keys:
            continue
        anchor = _matching_entity_anchor(row, matched_entity_ids)
        if anchor is None or anchor_counts.get(anchor, 0) >= per_entity_cap:
            continue
        seen_keys.add(row_key)
        selected.append(row)
        anchor_counts[anchor] = anchor_counts.get(anchor, 0) + 1
        if len(selected) >= reserve_count:
            break

    return selected[:reserve_count]

def _finalize_preview_rows(
    ordered_rows: List[Dict[str, Any]],
    topk: int,
    matched_entity_ids: Optional[set] = None,
) -> List[Dict[str, Any]]:
    if not ordered_rows or topk <= 0:
        return []

    neighborhood_rows = _entity_neighborhood_preview_rows(ordered_rows, topk, matched_entity_ids)
    neighborhood_keys = {canonical_row_key(row) for row in neighborhood_rows}
    remaining_rows = [
        row for row in ordered_rows
        if isinstance(row, dict) and canonical_row_key(row) not in neighborhood_keys
    ]
    remainder = _diversified_preview_rows(remaining_rows, max(0, topk - len(neighborhood_rows)))
    return (neighborhood_rows + remainder)[:topk]

def _compact_preview_output(
    rows: List[Dict[str, Any]],
    topk: int,
    *,
    matched_entity_ids: Optional[set] = None,
) -> List[Dict[str, Any]]:
    finalized = _finalize_preview_rows(rows, topk, matched_entity_ids=matched_entity_ids)
    return [_compact_row_for_prompt(row) for row in finalized[:topk]]

def _lexical_preview_rows(
    input_text: str,
    base_rows: List[Dict[str, Any]],
    topk: int,
) -> Tuple[List[Dict[str, Any]], set]:
    haystack = norm(input_text)
    selected: List[Dict[str, Any]] = []
    seen_keys = set()
    for row in base_rows:
        if not isinstance(row, dict):
            continue
        for label in (row.get("itemLabel"), row.get("valueLabel")):
            if label and norm(str(label)) in haystack and _try_add_preview_row(row, selected=selected, seen_keys=seen_keys):
                break
        if len(selected) >= topk:
            break
    return selected, seen_keys

def select_preview_rows(
    input_text: str,
    base_rows: List[Dict[str, Any]],
    topk: int,
    *,
    session_id: Optional[str] = None,
    kb_revision: int = 0,
    matched_entity_ids: Optional[set] = None,
    warnings: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    if not base_rows or topk <= 0:
        return []

    # Cheap exact-label hits are tried first; only the remainder goes through the more
    # expensive FTS + embedding rerank path.
    lexical, seen_keys = _lexical_preview_rows(input_text, base_rows, topk)
    if len(lexical) >= topk:
        return _compact_preview_output(lexical, topk, matched_entity_ids=matched_entity_ids)

    fts_limit = int(FTS_CANDIDATES) if isinstance(FTS_CANDIDATES, int) else 450
    if fts_limit <= 0:
        fts_limit = 450
    indexes = fts_candidate_indices(
        session_id=session_id,
        kb_revision=kb_revision,
        rows=base_rows,
        input_text=input_text,
        limit=fts_limit,
    )
    candidates = [
        base_rows[index]
        for index in indexes
        if isinstance(index, int) and 0 <= index < len(base_rows) and isinstance(base_rows[index], dict)
    ]
    if not candidates:
        candidates = [row for row in base_rows[:1200] if isinstance(row, dict)]
        if not candidates:
            return _compact_preview_output(lexical, topk, matched_entity_ids=matched_entity_ids)

    query_vectors = _embed_texts(
        [truncate_str(normalize_input_text(input_text), 1600)],
        warnings=warnings,
        purpose="query embedding",
    )
    if not query_vectors:
        # Degrade gracefully to lexical/FTS retrieval if embeddings are unavailable.
        combined = list(lexical)
        for row in candidates:
            _try_add_preview_row(row, selected=combined, seen_keys=seen_keys)
        return _compact_preview_output(combined, topk, matched_entity_ids=matched_entity_ids)

    rerank_limit = (
        EMBEDDING_RERANK_CANDIDATES
        if isinstance(EMBEDDING_RERANK_CANDIDATES, int) and EMBEDDING_RERANK_CANDIDATES > 0
        else len(candidates)
    )
    rerank_candidates = candidates[:rerank_limit]
    query_vec = query_vectors[0]
    texts: List[str] = []
    missing_keys: List[Tuple[Any, ...]] = []
    fresh_vectors: Dict[Tuple[Any, ...], List[float]] = {}
    for row in rerank_candidates:
        key = canonical_row_key(row)
        if _get_cached_row_embedding(key) is not None:
            continue
        missing_keys.append(key)
        texts.append(truncate_str(_row_text_for_embedding(row), 900))

    if texts:
        vectors = _embed_texts(
            texts,
            warnings=warnings,
            purpose="candidate row embeddings",
        )
        if vectors and len(vectors) == len(missing_keys):
            for key, vector in zip(missing_keys, vectors):
                fresh_vectors[key] = vector
                _store_row_embedding(key, vector)

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for row in rerank_candidates:
        key = canonical_row_key(row)
        vector = _get_cached_row_embedding(key) or fresh_vectors.get(key)
        if not vector:
            continue
        scored.append((_cosine_similarity(query_vec, vector), row))

    scored.sort(key=lambda item: item[0], reverse=True)
    ordered_rows: List[Dict[str, Any]] = list(lexical)
    for _, row in scored:
        _try_add_preview_row(row, selected=ordered_rows, seen_keys=seen_keys)

    return _compact_preview_output(ordered_rows, topk, matched_entity_ids=matched_entity_ids)
