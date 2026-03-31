"""Environment-backed configuration and client setup used across the backend."""

import os
from pathlib import Path
from openai import OpenAI
from . import tuning

def env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value else default

def env_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    return float(value) if value else default

TOPK = env_int("TOPK", tuning.TOPK)
FTS_CANDIDATES = env_int("FTS_CANDIDATES", tuning.FTS_CANDIDATES)
FTS_QUERY_MAX_TOKENS = env_int("FTS_QUERY_MAX_TOKENS", tuning.FTS_QUERY_MAX_TOKENS)
EMBEDDING_RERANK_CANDIDATES = env_int("EMBEDDING_RERANK_CANDIDATES", tuning.EMBEDDING_RERANK_CANDIDATES)
ENTITY_CATALOG_LIMIT = env_int("ENTITY_CATALOG_LIMIT", tuning.ENTITY_CATALOG_LIMIT)
ENTITY_NEIGHBORHOOD_SHARE = env_float("ENTITY_NEIGHBORHOOD_SHARE", tuning.ENTITY_NEIGHBORHOOD_SHARE)
ENTITY_NEIGHBORHOOD_PER_ENTITY = env_int("ENTITY_NEIGHBORHOOD_PER_ENTITY", tuning.ENTITY_NEIGHBORHOOD_PER_ENTITY)
ROW_EMBEDDING_CACHE_MAX = env_int("ROW_EMBEDDING_CACHE_MAX", tuning.ROW_EMBEDDING_CACHE_MAX)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", tuning.EMBEDDING_MODEL)
EXTRACTOR_MODEL = os.getenv("EXTRACTOR_MODEL", tuning.EXTRACTOR_MODEL)
EXTRACTOR_TEMPERATURE = env_float("EXTRACTOR_TEMPERATURE", tuning.EXTRACTOR_TEMPERATURE)
PORT = env_int("PORT", 8000)
HOST = os.getenv("HOST", "0.0.0.0")

ONTOLOGY_FILE = Path(os.getenv("ONTOLOGY_FILE", "user_data_editable/ontology.json"))
DEFAULT_QUERY_FILE = Path(os.getenv("DEFAULT_QUERY_FILE", "user_data_editable/query.json"))
ALLOW_DELETE = os.getenv("ALLOW_DELETE", "false").lower() == "true"

def get_client() -> OpenAI:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing OPENAI_API_KEY environment variable.")
    return OpenAI()
