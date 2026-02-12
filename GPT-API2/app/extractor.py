from __future__ import annotations
import json
from typing import List, Tuple
import numpy as np
from openai import OpenAI

from .config import EMBEDDING_MODEL, EXTRACTOR_MODEL, KB_PATH, TOPK, get_client
from .kb import build_label_maps, fix_labels, load_kb, row_key
from .prompts import extraction_instructions, kb_additions_schema


def embed_texts(
    client: OpenAI,
    texts: List[str],
    model: str,
    batch_size: int = 256,
) -> np.ndarray:
    """
    Return L2-normalized embeddings array shape (n, d).
    Uses dot-product similarity as cosine similarity after normalization.
    """
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)

    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        r = client.embeddings.create(model=model, input=batch)
        embeddings.extend([d.embedding for d in r.data])

    E = np.array(embeddings, dtype=np.float32)
    norms = np.linalg.norm(E, axis=1, keepdims=True) + 1e-12
    return E / norms


def retrieve_kb_context(section_text: str, kb: list, client: OpenAI) -> list:
    """Simple embedding retrieval over existing KB labels."""
    if not kb:
        return []

    kb_texts = [
        f"{r.get('itemLabel','')} | {r.get('propertyLabel','')} | {r.get('valueLabel','')}"
        for r in kb
    ]
    kb_emb = embed_texts(client, kb_texts, model=EMBEDDING_MODEL)
    q_emb = embed_texts(client, [section_text], model=EMBEDDING_MODEL)

    if kb_emb.size == 0 or q_emb.size == 0:
        return []

    q = q_emb[0]
    scores = kb_emb @ q
    top_idx = np.argsort(-scores)[: min(TOPK, len(kb))]
    return [kb[int(i)] for i in top_idx]


def connect_section(section_text: str) -> Tuple[List[dict], List[str]]:
    """
    Given input text, retrieve relevant KB rows and ask the model to propose
    strictly-JSON KB additions + short reasons.
    """
    client = get_client()
    kb = load_kb(KB_PATH)

    kb_context = retrieve_kb_context(section_text, kb, client)
    schema = kb_additions_schema()
    instructions = extraction_instructions()

    resp = client.chat.completions.create(
        model=EXTRACTOR_MODEL,
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
    additions = out.get("additions", []) or []
    reasons = out.get("reasons", []) or []

    existing = {row_key(r) for r in kb}
    seen_new = set()

    item_label, prop_label, value_label = build_label_maps(kb)
    clean_additions, clean_reasons = [], []

    for i, add in enumerate(additions):
        if not isinstance(add, dict):
            continue

        add = fix_labels(add, item_label, prop_label, value_label)
        k = row_key(add)

        if k in existing or k in seen_new:
            continue

        if not all(str(add.get(x, "")).strip() for x in ["itemLabel", "propertyLabel", "valueLabel"]):
            continue

        seen_new.add(k)
        clean_additions.append(add)
        clean_reasons.append(reasons[i] if i < len(reasons) else "")

    return clean_additions, clean_reasons

