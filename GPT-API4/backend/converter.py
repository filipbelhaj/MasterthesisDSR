from __future__ import annotations
from typing import Any, Iterable
from urllib.parse import urlparse

def tail_id(value: str) -> str:
    """Extract final path segment from a URL, else return unchanged text."""
    if not value:
        return ""
    if "://" not in value:
        return value
    path = urlparse(value).path.rstrip("/")
    return path.rsplit("/", 1)[-1] if path else value

def _escape_literal(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')

def _qs_term(token: str, placeholder_to_qs_target: dict[str, str]) -> str:
    if token.startswith(("QNEW", "NEW:")):
        return placeholder_to_qs_target.get(token, token)
    if token.startswith("Q"):
        return token
    return f'"{_escape_literal(token)}"'

def rows_to_quickstatements(rows: Iterable[dict[str, Any]], lang: str = "en") -> str:
    """Build importable QuickStatements from finalized rows."""
    lines: list[str] = []
    placeholder_to_qs_target: dict[str, str] = {}

    for row in rows:
        item = tail_id(str(row.get("item", "")))
        prop = tail_id(str(row.get("property", "")))
        value = tail_id(str(row.get("value", "")))
        if not (item and prop and value and prop.startswith("P")):
            continue

        if not (item.startswith("Q") or item.startswith(("QNEW", "NEW:"))):
            continue

        if item.startswith(("QNEW", "NEW:")) and item not in placeholder_to_qs_target:
            lines.append("CREATE")
            label = str(row.get("itemLabel", "")).strip()
            if label:
                lines.append(f'LAST\tL{lang}\t"{_escape_literal(label)}"')
            placeholder_to_qs_target[item] = "LAST"

        qs_item = placeholder_to_qs_target.get(item, item)
        qs_value = _qs_term(value, placeholder_to_qs_target)

        parts = [qs_item, prop, qs_value]

        qp = tail_id(str(row.get("qualifierProperty", "") or ""))
        qv = tail_id(str(row.get("qualifierValue", "") or ""))
        if qp and qv and qp.startswith("P"):
            parts.extend([qp, _qs_term(qv, placeholder_to_qs_target)])

        lines.append("\t".join(parts))

    return "\n".join(lines)