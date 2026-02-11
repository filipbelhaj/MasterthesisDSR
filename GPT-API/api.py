import os
import json
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI


"""\
Ontology Triple Extractor – API + UI (single-server).

This app serves:
  - GET /               -> index.html UI
  - POST /api/extract   -> JSON API (input_text -> qs_output + explain_output)

Run locally:
  1) Set your OpenAI key (do NOT hardcode it in code):
       export OPENAI_API_KEY="..."
  2) Start:
       python api.py
  3) Open:
       http://127.0.0.1:8000
"""


APP_DIR = Path(__file__).parent
KB_PATH = APP_DIR / "query.json"  # must sit next to api.py
TOPK = 20


def _client() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "Missing OPENAI_API_KEY env var. Example: export OPENAI_API_KEY='...'."
        )
    return OpenAI(api_key=key)



def load_kb(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        kb = json.load(f)
    if not isinstance(kb, list):
        raise ValueError("query.json must be a list of objects")
    return kb


def embed(client: OpenAI, texts, model: str = "text-embedding-3-small"):
    if not texts:
        # embedding size differs by model; we only use dot-products, so empty is fine
        return np.zeros((0, 1), dtype=np.float32)

    embeddings = []
    for i in range(0, len(texts), 2048):
        batch = texts[i : i + 2048]
        r = client.embeddings.create(model=model, input=batch)
        embeddings.extend([d.embedding for d in r.data])

    E = np.array(embeddings, dtype=np.float32)
    E /= (np.linalg.norm(E, axis=1, keepdims=True) + 1e-12)
    return E


def row_key(r):
    return (
        r.get("item", ""),
        r.get("property", ""),
        r.get("value", ""),
        r.get("qualifierProperty", ""),
        r.get("qualifierValue", ""),
    )


def build_label_maps(kb):
    item_label, prop_label, value_label = {}, {}, {}
    for r in kb:
        if r.get("item") and r.get("itemLabel"):
            item_label[r["item"]] = r["itemLabel"]
        if r.get("property") and r.get("propertyLabel"):
            prop_label[r["property"]] = r["propertyLabel"]
        if r.get("value") and r.get("valueLabel"):
            value_label[r["value"]] = r["valueLabel"]
    return item_label, prop_label, value_label


def fix_labels(add, item_label, prop_label, value_label):
    # For URIs already in KB, force canonical labels from KB
    if add.get("item") in item_label:
        add["itemLabel"] = item_label[add["item"]]
    if add.get("property") in prop_label:
        add["propertyLabel"] = prop_label[add["property"]]
    if add.get("value") in value_label:
        add["valueLabel"] = value_label[add["value"]]

    # Also qualifiers (if present)
    if add.get("qualifierProperty") in prop_label:
        add["qualifierPropertyLabel"] = prop_label[add["qualifierProperty"]]
    if add.get("qualifierValue") in value_label:
        add["qualifierValueLabel"] = value_label[add["qualifierValue"]]
    return add


def connect_section(section_text: str):
    client = _client()
    kb = load_kb(KB_PATH)

    # 1) Retrieve relevant KB context (simple RAG)
    kb_texts = [
        f"{r.get('itemLabel','')} | {r.get('propertyLabel','')} | {r.get('valueLabel','')}"
        for r in kb
    ]
    kb_emb = embed(client, kb_texts)
    q_emb = embed(client, [section_text])[0]
    scores = kb_emb @ q_emb
    top_idx = np.argsort(-scores)[:TOPK]
    kb_context = [kb[i] for i in top_idx]

    # 2) Ask model for additions + short reasons (STRICT JSON)
    schema = {
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

    instructions = (
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

    # NOTE: set the model you actually have access to.
    resp = client.chat.completions.create(
        model=os.getenv("EXTRACTOR_MODEL", "gpt-5.2"),
        messages=[
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": json.dumps(
                    {"SECTION": section_text, "KB_CONTEXT": kb_context},
                    ensure_ascii=False,
                ),
            },
        ],
        response_format={"type": "json_schema", "json_schema": schema},
    )

    out = json.loads(resp.choices[0].message.content)
    additions = out.get("additions", [])
    reasons = out.get("reasons", [])

    # 3) Remove duplicates vs original KB and within new additions; fix labels
    existing = {row_key(r) for r in kb}
    seen_new = set()
    item_label, prop_label, value_label = build_label_maps(kb)

    clean_additions, clean_reasons = [], []
    for i, add in enumerate(additions):
        add = fix_labels(add, item_label, prop_label, value_label)

        k = row_key(add)
        if k in existing or k in seen_new:
            continue

        # Minimal sanity: required labels non-empty
        if not all(add.get(x, "").strip() for x in ["itemLabel", "propertyLabel", "valueLabel"]):
            continue

        seen_new.add(k)
        clean_additions.append(add)
        clean_reasons.append(reasons[i] if i < len(reasons) else "")

    return clean_additions, clean_reasons


def to_quickstatements(additions):
    """Very simple QS-like TSV rows.

    Format:
      item<TAB>property<TAB>value[<TAB>qualProp<TAB>qualVal]
    """
    lines = []
    for a in additions:
        row = [a.get("item", ""), a.get("property", ""), a.get("value", "")]
        if a.get("qualifierProperty") and a.get("qualifierValue"):
            row += [a["qualifierProperty"], a["qualifierValue"]]
        lines.append("\t".join(row))
    return "\n".join(lines)


def reasons_text(reasons):
    return "\n".join(f"- {r}" for r in reasons if str(r).strip())


app = Flask(__name__, static_folder=".", static_url_path="")


@app.get("/")
def ui():
    # Serve index.html from the same folder as api.py
    return send_from_directory(APP_DIR, "index.html")


@app.post("/api/extract")
def api_extract():
    payload = request.get_json(silent=True) or {}
    input_text = (payload.get("input_text") or "").strip()
    if not input_text:
        return jsonify({"error": "input_text is required"}), 400

    try:
        additions, reasons = connect_section(input_text)
        return jsonify(
            {
                "qs_output": json.dumps(additions, ensure_ascii=False, indent=2),
                "explain_output": reasons_text(reasons),
                "additions": additions,
                "reasons": reasons,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)

