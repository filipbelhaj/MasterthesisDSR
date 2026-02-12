import json
from flask import Blueprint, jsonify, request, send_from_directory
from .config import BASE_DIR
from .extractor import connect_section

bp = Blueprint("routes", __name__)

def to_quickstatements(additions) -> str:
    """Very simple QS-like TSV rows: item<TAB>property<TAB>value[<TAB>qualProp<TAB>qualVal]"""
    lines = []
    for a in additions:
        row = [a.get("item", ""), a.get("property", ""), a.get("value", "")]
        qp, qv = a.get("qualifierProperty"), a.get("qualifierValue")
        if qp and qv:
            row += [qp, qv]
        lines.append("\t".join(row))
    return "\n".join(lines)


def reasons_text(reasons) -> str:
    return "\n".join(f"- {r}" for r in reasons if str(r).strip())


@bp.get("/")
def ui():
    return send_from_directory(BASE_DIR, "index.html")


@bp.post("/api/extract")
def api_extract():
    payload = request.get_json(silent=True) or {}
    input_text = (payload.get("input_text") or "").strip()
    if not input_text:
        return jsonify(error="input_text is required"), 400

    try:
        additions, reasons = connect_section(input_text)
        return jsonify(
            qs_output=json.dumps(additions, ensure_ascii=False, indent=2),
            explain_output=reasons_text(reasons),
            additions=additions,
            reasons=reasons,
        )
    except Exception as e:
        return jsonify(error=str(e)), 500


@bp.get("/health")
def health():
    return jsonify(ok=True)
